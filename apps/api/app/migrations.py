"""Versioned PostgreSQL migration runner for deployment and CI."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from app.config import get_settings


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION_NAME = re.compile(r"^(?P<version>\d{3})_[a-z0-9_]+\.sql$")
DATABASE_CONNECT_TIMEOUT_SECONDS = 5


class MigrationError(RuntimeError):
    """Raised when migration discovery or execution is unsafe."""


@dataclass(frozen=True)
class Migration:
    version: str
    filename: str
    checksum: str
    sql: str


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    seen_versions: set[str] = set()

    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        version = match.group("version")
        if version in seen_versions:
            raise MigrationError(f"Duplicate migration version: {version}")
        seen_versions.add(version)
        content = path.read_bytes()
        migrations.append(
            Migration(
                version=version,
                filename=path.name,
                checksum=hashlib.sha256(content).hexdigest(),
                sql=content.decode("utf-8"),
            )
        )

    if not migrations:
        raise MigrationError(f"No migrations found in {directory}")
    return migrations


def run_migrations(
    database_url: str,
    *,
    directory: Path = MIGRATIONS_DIR,
) -> list[str]:
    """Apply pending migrations and return the filenames applied this run."""
    if not database_url.strip():
        raise MigrationError("DATABASE_URL is required to run migrations.")

    import psycopg

    migrations = discover_migrations(directory)
    applied_now: list[str] = []

    with psycopg.connect(
        database_url,
        connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
    ) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.commit()
        connection.execute(
            "SELECT pg_advisory_lock(hashtext('applylens_schema_migrations'))"
        )

        try:
            rows = connection.execute(
                "SELECT version, filename, checksum FROM schema_migrations"
            ).fetchall()
            applied = {
                str(version): (str(filename), str(checksum))
                for version, filename, checksum in rows
            }

            for migration in migrations:
                previous = applied.get(migration.version)
                if previous is not None:
                    previous_filename, previous_checksum = previous
                    if (
                        previous_filename != migration.filename
                        or previous_checksum != migration.checksum
                    ):
                        raise MigrationError(
                            "Applied migration differs from repository: "
                            f"{migration.version}"
                        )
                    continue

                try:
                    connection.execute(migration.sql)
                    connection.execute(
                        """
                        INSERT INTO schema_migrations (version, filename, checksum)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            migration.version,
                            migration.filename,
                            migration.checksum,
                        ),
                    )
                    connection.commit()
                except Exception as error:
                    connection.rollback()
                    raise MigrationError(
                        f"Migration failed: {migration.filename}"
                    ) from error

                applied_now.append(migration.filename)
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtext('applylens_schema_migrations'))"
            )
            connection.commit()

    return applied_now


def main() -> None:
    database_url = get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is required to run migrations.")

    applied = run_migrations(database_url)
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database schema is current.")


if __name__ == "__main__":
    main()
