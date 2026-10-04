from pathlib import Path

import pytest

from app.migrations import MigrationError, discover_migrations


def write_migration(directory: Path, filename: str, sql: str = "SELECT 1;") -> None:
    (directory / filename).write_text(sql, encoding="utf-8")


def test_discovers_repository_migrations_in_version_order() -> None:
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == [
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
        "007",
        "008",
        "009",
        "010",
    ]
    assert all(len(migration.checksum) == 64 for migration in migrations)


def test_migration_checksum_changes_when_sql_changes(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_first.sql")
    first_checksum = discover_migrations(tmp_path)[0].checksum

    write_migration(tmp_path, "001_first.sql", "SELECT 2;")

    assert discover_migrations(tmp_path)[0].checksum != first_checksum


def test_rejects_invalid_migration_filename(tmp_path: Path) -> None:
    write_migration(tmp_path, "migration.sql")

    with pytest.raises(MigrationError, match="Invalid migration filename"):
        discover_migrations(tmp_path)


def test_rejects_duplicate_migration_versions(tmp_path: Path) -> None:
    write_migration(tmp_path, "001_first.sql")
    write_migration(tmp_path, "001_second.sql")

    with pytest.raises(MigrationError, match="Duplicate migration version"):
        discover_migrations(tmp_path)


def test_rejects_empty_migration_directory(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="No migrations found"):
        discover_migrations(tmp_path)
