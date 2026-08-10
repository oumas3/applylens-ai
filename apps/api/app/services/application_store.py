"""PostgreSQL persistence for user-owned application records.

The routers keep their existing in-memory representations for the local JSON
fallback and request-level behavior. When DATABASE_URL is configured, this
store loads and persists the same records in PostgreSQL.
"""

from collections.abc import Iterable
from datetime import date, datetime
import json
from typing import Any


DATABASE_CONNECT_TIMEOUT_SECONDS = 3


class PostgresApplicationStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _json_param(value: Any) -> Any:
        from psycopg.types.json import Jsonb

        return Jsonb(value)

    @classmethod
    def _record_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def check(self) -> None:
        """Raise if PostgreSQL or the application schema is unavailable."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT to_regclass('public.users') AS users,
                       to_regclass('public.sessions') AS sessions,
                       to_regclass('public.login_attempts') AS login_attempts,
                       to_regclass('public.password_reset_tokens') AS password_reset_tokens,
                       to_regclass('public.documents') AS documents,
                       to_regclass('public.opportunities') AS opportunities,
                       to_regclass('public.reviews') AS reviews,
                       to_regclass('public.tasks') AS tasks
                """
            ).fetchone()
            missing = [
                name
                for name in (
                    "users",
                    "sessions",
                    "login_attempts",
                    "password_reset_tokens",
                    "documents",
                    "opportunities",
                    "reviews",
                    "tasks",
                )
                if not row or row[name] is None
            ]
            if missing:
                raise RuntimeError(
                    "Application database schema is missing: " + ", ".join(missing)
                )

    def load_documents(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT id, user_id, original_filename, stored_filename, category,
                           content_type, size_bytes, status, extracted_text_length, uploaded_at
                    FROM documents
                    ORDER BY uploaded_at, id
                    """
                ).fetchall()
            )

    def replace_documents(
        self,
        records: Iterable[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        values = list(records)
        with self._connect() as connection:
            if user_id is None:
                connection.execute("DELETE FROM documents")
            else:
                connection.execute("DELETE FROM documents WHERE user_id = %s", (user_id,))
            for record in values:
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, user_id, original_filename, stored_filename, category,
                        content_type, size_bytes, status, extracted_text_length, uploaded_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["id"], record["user_id"], record["original_filename"],
                        record["stored_filename"], record["category"], record["content_type"],
                        record["size_bytes"], record["status"], record["extracted_text_length"],
                        self._json_value(record["uploaded_at"]),
                    ),
                )

    def load_opportunities(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, title, source_text, institution, degree_type,
                       source_name, source_url, requirements, requirement_citations,
                       deadline, deadline_date, funding
                FROM opportunities
                ORDER BY id
                """
            ).fetchall()
        return [
            {
                **row,
                "requirements": self._record_value(row["requirements"]),
                "requirement_citations": self._record_value(row["requirement_citations"]),
            }
            for row in rows
        ]

    def replace_opportunities(
        self,
        records: Iterable[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        values = list(records)
        with self._connect() as connection:
            if user_id is None:
                connection.execute("DELETE FROM opportunities")
            else:
                connection.execute("DELETE FROM opportunities WHERE user_id = %s", (user_id,))
            for record in values:
                connection.execute(
                    """
                    INSERT INTO opportunities (
                        id, user_id, title, source_text, institution, degree_type,
                        source_name, source_url, requirements, requirement_citations,
                        deadline, deadline_date, funding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["id"], record["user_id"], record["title"], record["source_text"],
                        record["institution"], record["degree_type"], record["source_name"],
                        str(record["source_url"]) if record["source_url"] is not None else None,
                        self._json_param(record["requirements"]),
                        self._json_param(record["requirement_citations"]),
                        record["deadline"], self._json_value(record["deadline_date"]), record["funding"],
                    ),
                )

    def load_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT user_id, id, title, eligibility, matched_requirements,
                       missing_requirements, deadline, funding
                FROM reviews
                ORDER BY user_id, id
                """
            ).fetchall()
        return [
            {
                **row,
                "matched_requirements": self._record_value(row["matched_requirements"]),
                "missing_requirements": self._record_value(row["missing_requirements"]),
            }
            for row in rows
        ]

    def replace_reviews(
        self,
        records: Iterable[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        values = list(records)
        with self._connect() as connection:
            if user_id is None:
                connection.execute("DELETE FROM reviews")
            else:
                connection.execute("DELETE FROM reviews WHERE user_id = %s", (user_id,))
            for record in values:
                connection.execute(
                    """
                    INSERT INTO reviews (
                        user_id, id, title, eligibility, matched_requirements,
                        missing_requirements, deadline, funding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["user_id"], record["id"], record["title"], record["eligibility"],
                        self._json_param(record["matched_requirements"]),
                        self._json_param(record["missing_requirements"]),
                        record["deadline"], record["funding"],
                    ),
                )

    def load_tasks(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT user_id, id, opportunity_id, title, status
                    FROM tasks
                    ORDER BY user_id, id
                    """
                ).fetchall()
            )

    def replace_tasks(
        self,
        records: Iterable[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        values = list(records)
        with self._connect() as connection:
            if user_id is None:
                connection.execute("DELETE FROM tasks")
            else:
                connection.execute("DELETE FROM tasks WHERE user_id = %s", (user_id,))
            for record in values:
                connection.execute(
                    """
                    INSERT INTO tasks (user_id, id, opportunity_id, title, status)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        record["user_id"], record["id"], record["opportunity_id"],
                        record["title"], record["status"],
                    ),
                )
