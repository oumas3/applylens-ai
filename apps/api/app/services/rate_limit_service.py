"""Persistent fixed-window limits for abuse-sensitive API actions."""

from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import sqlite3


DATABASE_CONNECT_TIMEOUT_SECONDS = 3
RATE_LIMIT_RETENTION_SECONDS = 2 * 24 * 60 * 60


class RateLimitService:
    def __init__(self, database_path: Path, database_url: str | None = None) -> None:
        self.database_path = database_path
        self.database_url = database_url
        if self.database_url is None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _postgres(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "psycopg is required for PostgreSQL rate limiting."
            ) from error
        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS request_limits (
                    limit_key TEXT PRIMARY KEY,
                    request_count INTEGER NOT NULL,
                    window_started TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS request_limits_window_started_idx
                    ON request_limits (window_started);
                """
            )

    @staticmethod
    def limit_key(action: str, identity: str) -> str:
        value = f"{action}\0{identity}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_utc_datetime(value: datetime | str) -> datetime:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _row(connection, limit_key: str, *, postgres: bool):
        placeholder = "%s" if postgres else "?"
        return connection.execute(
            f"""
            SELECT request_count, window_started
            FROM request_limits
            WHERE limit_key = {placeholder}
            """,
            (limit_key,),
        ).fetchone()

    @staticmethod
    def _cleanup(connection, *, postgres: bool, now: datetime) -> int:
        placeholder = "%s" if postgres else "?"
        cutoff = now - timedelta(seconds=RATE_LIMIT_RETENTION_SECONDS)
        cursor = connection.execute(
            f"DELETE FROM request_limits WHERE window_started < {placeholder}",
            (cutoff.isoformat(),),
        )
        return cursor.rowcount

    @classmethod
    def _next_window(
        cls,
        row,
        *,
        limit: int,
        window_seconds: int,
        now: datetime,
    ) -> tuple[int, datetime, int | None]:
        if row is not None:
            window_started = cls._as_utc_datetime(row["window_started"])
            window_ends = window_started + timedelta(seconds=window_seconds)
            if window_ends > now:
                request_count = int(row["request_count"])
                if request_count >= limit:
                    retry_after = max(
                        1,
                        math.ceil((window_ends - now).total_seconds()),
                    )
                    return request_count, window_started, retry_after
                return request_count + 1, window_started, None
        return 1, now, None

    def consume(
        self,
        limit_key: str,
        *,
        limit: int,
        window_seconds: int,
        now: datetime | None = None,
    ) -> int | None:
        """Consume one request and return Retry-After seconds when blocked."""
        current_time = now or datetime.now(timezone.utc)
        if self.database_url:
            with self._postgres() as connection:
                self._cleanup(connection, postgres=True, now=current_time)
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (limit_key,),
                )
                row = self._row(connection, limit_key, postgres=True)
                count, started, retry_after = self._next_window(
                    row,
                    limit=limit,
                    window_seconds=window_seconds,
                    now=current_time,
                )
                if retry_after is None:
                    connection.execute(
                        """
                        INSERT INTO request_limits (
                            limit_key, request_count, window_started
                        ) VALUES (%s, %s, %s)
                        ON CONFLICT (limit_key) DO UPDATE SET
                            request_count = EXCLUDED.request_count,
                            window_started = EXCLUDED.window_started
                        """,
                        (limit_key, count, started.isoformat()),
                    )
                return retry_after

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, postgres=False, now=current_time)
            row = self._row(connection, limit_key, postgres=False)
            count, started, retry_after = self._next_window(
                row,
                limit=limit,
                window_seconds=window_seconds,
                now=current_time,
            )
            if retry_after is None:
                connection.execute(
                    """
                    INSERT INTO request_limits (
                        limit_key, request_count, window_started
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(limit_key) DO UPDATE SET
                        request_count = excluded.request_count,
                        window_started = excluded.window_started
                    """,
                    (limit_key, count, started.isoformat()),
                )
            return retry_after

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current_time = now or datetime.now(timezone.utc)
        postgres = bool(self.database_url)
        connection_factory = self._postgres if postgres else self._connect
        with connection_factory() as connection:
            return self._cleanup(
                connection,
                postgres=postgres,
                now=current_time,
            )
