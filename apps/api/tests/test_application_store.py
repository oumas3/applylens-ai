import psycopg
import pytest

from app.services.application_store import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    PostgresApplicationStore,
)


def test_postgres_connections_have_a_bounded_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}
    connection = object()

    def fake_connect(database_url: str, **kwargs):
        captured["database_url"] = database_url
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(psycopg, "connect", fake_connect)

    result = PostgresApplicationStore("postgresql://postgres/applylens")._connect()

    assert result is connection
    assert captured["database_url"] == "postgresql://postgres/applylens"
    assert captured["connect_timeout"] == DATABASE_CONNECT_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "missing_table",
    [
        "login_attempts",
        "password_reset_tokens",
        "request_limits",
        "candidate_profiles",
    ],
)
def test_schema_check_requires_auth_security_tables(monkeypatch, missing_table: str) -> None:
    class Result:
        @staticmethod
        def fetchone():
            tables = {
                "users": "users",
                "sessions": "sessions",
                "login_attempts": "login_attempts",
                "password_reset_tokens": "password_reset_tokens",
                "request_limits": "request_limits",
                "documents": "documents",
                "opportunities": "opportunities",
                "reviews": "reviews",
                "tasks": "tasks",
                "candidate_profiles": "candidate_profiles",
            }
            tables[missing_table] = None
            return tables

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def execute(_query: str):
            return Result()

    store = PostgresApplicationStore("postgresql://postgres/applylens")
    monkeypatch.setattr(store, "_connect", Connection)

    with pytest.raises(RuntimeError, match=missing_table):
        store.check()
