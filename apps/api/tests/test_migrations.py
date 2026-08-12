from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "002_application_data.sql"
LOGIN_ATTEMPTS_MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "003_login_attempts.sql"
)
PASSWORD_RESET_MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "004_password_reset_tokens.sql"
)
ACCOUNT_PRIVACY_MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "005_account_privacy.sql"
)


def test_application_data_migration_defines_required_tables_and_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for table in ("users", "sessions", "documents", "opportunities", "reviews", "tasks"):
        assert f"create table if not exists {table}" in sql

    for index in (
        "documents_user_id_idx",
        "opportunities_user_id_idx",
        "reviews_user_id_idx",
        "tasks_user_id_idx",
    ):
        assert f"create index if not exists {index}" in sql


def test_application_data_migration_enforces_user_ownership() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "user_id text not null references users(id) on delete cascade" in sql
    assert "primary key (user_id, id)" in sql


def test_login_attempt_migration_is_idempotent_and_indexed() -> None:
    sql = LOGIN_ATTEMPTS_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists login_attempts" in sql
    assert "attempt_key text primary key" in sql
    assert "create index if not exists login_attempts_blocked_until_idx" in sql
    assert "create index if not exists login_attempts_window_started_idx" in sql


def test_password_reset_migration_is_idempotent_owned_and_indexed() -> None:
    sql = PASSWORD_RESET_MIGRATION.read_text(encoding="utf-8").lower()

    assert "create table if not exists password_reset_tokens" in sql
    assert "token_hash text primary key" in sql
    assert "user_id text not null references users(id) on delete cascade" in sql
    assert "create unique index if not exists password_reset_tokens_user_id_idx" in sql
    assert "create index if not exists password_reset_tokens_expires_at_idx" in sql


def test_account_privacy_migration_adds_explicit_consent_default() -> None:
    sql = ACCOUNT_PRIVACY_MIGRATION.read_text(encoding="utf-8").lower()

    assert "add column if not exists external_ai_consent" in sql
    assert "not null default false" in sql
