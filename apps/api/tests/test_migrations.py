from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "002_application_data.sql"


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
