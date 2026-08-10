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


def test_schema_check_requires_login_attempt_table(monkeypatch) -> None:
    class Result:
        @staticmethod
        def fetchone():
            return {
                "users": "users",
                "sessions": "sessions",
                "login_attempts": None,
                "documents": "documents",
                "opportunities": "opportunities",
                "reviews": "reviews",
                "tasks": "tasks",
            }

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

    with pytest.raises(RuntimeError, match="login_attempts"):
        store.check()
