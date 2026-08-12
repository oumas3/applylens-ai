from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from app.services.auth_service import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DUMMY_PASSWORD_HASH,
    LOGIN_ATTEMPT_LIMIT,
    LOGIN_ATTEMPT_RETENTION_SECONDS,
    LOGIN_BLOCK_SECONDS,
    PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS,
    PASSWORD_RESET_TOKEN_TTL_SECONDS,
    AuthService,
)


def test_postgres_auth_connections_have_a_bounded_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}
    connection = object()

    def fake_connect(database_url: str, **kwargs):
        captured["database_url"] = database_url
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(psycopg, "connect", fake_connect)

    service = AuthService(Path("unused.db"), "postgresql://postgres/applylens")
    result = service._postgres()

    assert result is connection
    assert captured["database_url"] == "postgresql://postgres/applylens"
    assert captured["connect_timeout"] == DATABASE_CONNECT_TIMEOUT_SECONDS


def test_unknown_email_still_performs_password_verification(
    tmp_path,
    monkeypatch,
) -> None:
    service = AuthService(tmp_path / "auth.db")
    captured: dict[str, str] = {}

    def fake_verify(password: str, encoded: str) -> bool:
        captured["password"] = password
        captured["encoded"] = encoded
        return False

    monkeypatch.setattr(service, "_verify_password", fake_verify)

    assert service.authenticate("missing@example.com", "wrong password") is None
    assert captured == {
        "password": "wrong password",
        "encoded": DUMMY_PASSWORD_HASH,
    }


def test_login_attempt_key_is_stable_and_source_specific() -> None:
    first = AuthService.login_attempt_key("Candidate@Example.com", "192.0.2.1")
    same_identity = AuthService.login_attempt_key("candidate@example.com", "192.0.2.1")
    different_source = AuthService.login_attempt_key("candidate@example.com", "192.0.2.2")

    assert first == same_identity
    assert first != different_source
    assert "candidate@example.com" not in first


def test_login_failure_history_can_be_cleared(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    attempt_key = service.login_attempt_key("candidate@example.com", "192.0.2.1")
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    for _ in range(LOGIN_ATTEMPT_LIMIT - 1):
        assert service.record_failed_login(attempt_key, now=now) is None
    assert service.record_failed_login(attempt_key, now=now) == LOGIN_BLOCK_SECONDS

    service.clear_login_failures(attempt_key)

    assert service.login_retry_after(attempt_key, now=now) is None
    assert service.record_failed_login(attempt_key, now=now) is None


def test_expired_login_block_starts_a_new_attempt_window(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    attempt_key = service.login_attempt_key("candidate@example.com", "192.0.2.1")
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    for _ in range(LOGIN_ATTEMPT_LIMIT):
        service.record_failed_login(attempt_key, now=now)
    after_block = now + timedelta(seconds=LOGIN_BLOCK_SECONDS + 1)

    assert service.login_retry_after(attempt_key, now=after_block) is None
    assert service.record_failed_login(attempt_key, now=after_block) is None


def test_recording_failure_removes_stale_attempt_rows(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    stale_key = service.login_attempt_key("stale@example.com", "192.0.2.1")
    current_key = service.login_attempt_key("current@example.com", "192.0.2.2")
    started_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    service.record_failed_login(stale_key, now=started_at)

    cleanup_time = started_at + timedelta(
        seconds=LOGIN_ATTEMPT_RETENTION_SECONDS + 1
    )
    service.record_failed_login(current_key, now=cleanup_time)

    with service._connect() as connection:
        stale_row = connection.execute(
            "SELECT attempt_key FROM login_attempts WHERE attempt_key = ?",
            (stale_key,),
        ).fetchone()
    assert stale_row is None


def test_password_reset_token_is_hashed_and_single_use(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    user = service.create_user("candidate@example.com", "correct horse battery")
    session_id = service.create_session(str(user["id"]))
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    token = service.create_password_reset_token(
        "candidate@example.com",
        now=now,
    )

    assert token is not None
    with service._connect() as connection:
        row = connection.execute(
            "SELECT token_hash FROM password_reset_tokens"
        ).fetchone()
    assert row is not None
    assert row["token_hash"] == service._hash_reset_token(token)
    assert row["token_hash"] != token

    assert service.reset_password(
        token,
        "a different secure password",
        now=now,
    )
    assert service.reset_password(
        token,
        "another secure password",
        now=now,
    ) is False
    assert service.get_user_by_session(session_id) is None
    assert service.authenticate("candidate@example.com", "correct horse battery") is None
    assert service.authenticate(
        "candidate@example.com",
        "a different secure password",
    ) is not None


def test_password_reset_token_expires_without_changing_password(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    service.create_user("candidate@example.com", "correct horse battery")
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    token = service.create_password_reset_token("candidate@example.com", now=now)

    assert token is not None
    assert service.reset_password(
        token,
        "a different secure password",
        now=now + timedelta(seconds=PASSWORD_RESET_TOKEN_TTL_SECONDS),
    ) is False
    assert service.authenticate(
        "candidate@example.com",
        "correct horse battery",
    ) is not None


def test_password_reset_requests_are_cooled_down_and_replace_old_tokens(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    service.create_user("candidate@example.com", "correct horse battery")
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    first = service.create_password_reset_token("candidate@example.com", now=now)

    assert first is not None
    assert service.create_password_reset_token(
        "candidate@example.com",
        now=now + timedelta(seconds=PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS - 1),
    ) is None
    replacement = service.create_password_reset_token(
        "candidate@example.com",
        now=now + timedelta(seconds=PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS),
    )
    assert replacement is not None
    assert replacement != first
    assert service.reset_password(
        first,
        "a different secure password",
        now=now + timedelta(seconds=PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS),
    ) is False


def test_unknown_email_does_not_create_a_password_reset_record(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")

    assert service.create_password_reset_token("missing@example.com") is None
    with service._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM password_reset_tokens"
        ).fetchone()[0]
    assert count == 0


def test_delete_user_cascades_local_sessions_and_reset_tokens(tmp_path) -> None:
    service = AuthService(tmp_path / "auth.db")
    user = service.create_user("candidate@example.com", "correct horse battery")
    user_id = str(user["id"])
    service.create_session(user_id)
    assert service.create_password_reset_token("candidate@example.com") is not None

    assert service.delete_user(user_id) is True

    with service._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM password_reset_tokens"
        ).fetchone()[0] == 0
