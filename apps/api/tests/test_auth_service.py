from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from app.services.auth_service import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DUMMY_PASSWORD_HASH,
    LOGIN_ATTEMPT_LIMIT,
    LOGIN_ATTEMPT_RETENTION_SECONDS,
    LOGIN_BLOCK_SECONDS,
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
