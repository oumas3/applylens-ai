import psycopg

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
