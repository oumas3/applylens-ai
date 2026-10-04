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
                       to_regclass('public.request_limits') AS request_limits,
                       to_regclass('public.documents') AS documents,
                       to_regclass('public.opportunities') AS opportunities,
                       to_regclass('public.reviews') AS reviews,
                       to_regclass('public.tasks') AS tasks,
                       to_regclass('public.candidate_profiles') AS candidate_profiles
                """
            ).fetchone()
            missing = [
                name
                for name in (
                    "users",
                    "sessions",
                    "login_attempts",
                    "password_reset_tokens",
                    "request_limits",
                    "documents",
                    "opportunities",
                    "reviews",
                    "tasks",
                    "candidate_profiles",
                )
                if not row or row[name] is None
            ]
            if missing:
                raise RuntimeError(
                    "Application database schema is missing: " + ", ".join(missing)
                )

    @staticmethod
    def _lock_user(connection, resource: str, user_id: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"{resource}:{user_id}",),
        )

    def load_documents(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            where = "" if user_id is None else "WHERE user_id = %s"
            parameters = () if user_id is None else (user_id,)
            rows = list(
                connection.execute(
                    f"""
                    SELECT id, user_id, original_filename, stored_filename, category,
                           content_type, size_bytes, status, extracted_text_length,
                           extracted_text, extracted_pages, uploaded_at
                    FROM documents
                    {where}
                    ORDER BY uploaded_at, id
                    """,
                    parameters,
                ).fetchall()
            )
        return [
            {
                **row,
                "extracted_pages": self._record_value(row["extracted_pages"]),
            }
            for row in rows
        ]

    def create_document(self, record: dict[str, Any], *, limit: int) -> bool:
        user_id = str(record["user_id"])
        with self._connect() as connection:
            self._lock_user(connection, "documents", user_id)
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM documents WHERE user_id = %s",
                (user_id,),
            ).fetchone()["count"]
            if int(count) >= limit:
                return False
            connection.execute(
                """
                INSERT INTO documents (
                    id, user_id, original_filename, stored_filename, category,
                    content_type, size_bytes, status, extracted_text_length,
                    extracted_text, extracted_pages, uploaded_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record["id"], user_id, record["original_filename"],
                    record["stored_filename"], record["category"],
                    record["content_type"], record["size_bytes"], record["status"],
                    record["extracted_text_length"], record.get("extracted_text"),
                    self._json_param(record.get("extracted_pages", [])),
                    self._json_value(record["uploaded_at"]),
                ),
            )
        return True

    def delete_document(self, user_id: str, document_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM documents WHERE user_id = %s AND id = %s",
                (user_id, document_id),
            )
            return cursor.rowcount == 1

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
                        content_type, size_bytes, status, extracted_text_length,
                        extracted_text, extracted_pages, uploaded_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["id"], record["user_id"], record["original_filename"],
                        record["stored_filename"], record["category"], record["content_type"],
                        record["size_bytes"], record["status"], record["extracted_text_length"],
                        record.get("extracted_text"),
                        self._json_param(record.get("extracted_pages", [])),
                        self._json_value(record["uploaded_at"]),
                    ),
                )

    def load_opportunities(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            where = "" if user_id is None else "WHERE user_id = %s"
            parameters = () if user_id is None else (user_id,)
            rows = connection.execute(
                f"""
                SELECT id, user_id, title, source_text, institution, degree_type,
                       source_name, source_url, requirements, requirement_citations,
                       deadline, deadline_date, funding
                FROM opportunities
                {where}
                ORDER BY id
                """,
                parameters,
            ).fetchall()
        return [
            {
                **row,
                "requirements": self._record_value(row["requirements"]),
                "requirement_citations": self._record_value(row["requirement_citations"]),
            }
            for row in rows
        ]

    def create_opportunity(self, record: dict[str, Any], *, limit: int) -> bool:
        user_id = str(record["user_id"])
        with self._connect() as connection:
            self._lock_user(connection, "opportunities", user_id)
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM opportunities WHERE user_id = %s",
                (user_id,),
            ).fetchone()["count"]
            if int(count) >= limit:
                return False
            connection.execute(
                """
                INSERT INTO opportunities (
                    id, user_id, title, source_text, institution, degree_type,
                    source_name, source_url, requirements, requirement_citations,
                    deadline, deadline_date, funding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record["id"], user_id, record["title"], record["source_text"],
                    record["institution"], record["degree_type"], record["source_name"],
                    str(record["source_url"]) if record["source_url"] is not None else None,
                    self._json_param(record["requirements"]),
                    self._json_param(record["requirement_citations"]),
                    record["deadline"], self._json_value(record["deadline_date"]),
                    record["funding"],
                ),
            )
        return True

    def update_opportunity_citations(
        self,
        user_id: str,
        opportunity_id: str,
        citations: list[dict[str, Any]],
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE opportunities
                SET requirement_citations = %s
                WHERE user_id = %s AND id = %s
                """,
                (self._json_param(citations), user_id, opportunity_id),
            )
            return cursor.rowcount == 1

    def delete_opportunity(self, user_id: str, opportunity_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM opportunities WHERE user_id = %s AND id = %s",
                (user_id, opportunity_id),
            )
            return cursor.rowcount == 1

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

    def load_reviews(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            where = "" if user_id is None else "WHERE user_id = %s"
            parameters = () if user_id is None else (user_id,)
            rows = connection.execute(
                f"""
                SELECT user_id, id, title, eligibility, matched_requirements,
                       missing_requirements, deadline, funding
                FROM reviews
                {where}
                ORDER BY user_id, id
                """,
                parameters,
            ).fetchall()
        return [
            {
                **row,
                "matched_requirements": self._record_value(row["matched_requirements"]),
                "missing_requirements": self._record_value(row["missing_requirements"]),
            }
            for row in rows
        ]

    def create_review(
        self,
        record: dict[str, Any],
        *,
        limit: int,
    ) -> str:
        user_id = str(record["user_id"])
        with self._connect() as connection:
            self._lock_user(connection, "reviews", user_id)
            exists = connection.execute(
                "SELECT 1 AS present FROM reviews WHERE user_id = %s AND id = %s",
                (user_id, record["id"]),
            ).fetchone()
            if exists:
                return "duplicate"
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM reviews WHERE user_id = %s",
                (user_id,),
            ).fetchone()["count"]
            if int(count) >= limit:
                return "quota"
            connection.execute(
                """
                INSERT INTO reviews (
                    user_id, id, title, eligibility, matched_requirements,
                    missing_requirements, deadline, funding
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, record["id"], record["title"], record["eligibility"],
                    self._json_param(record["matched_requirements"]),
                    self._json_param(record["missing_requirements"]),
                    record["deadline"], record["funding"],
                ),
            )
        return "created"

    def delete_review(self, user_id: str, review_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM reviews WHERE user_id = %s AND id = %s",
                (user_id, review_id),
            )
            return cursor.rowcount == 1

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

    def load_tasks(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            where = "" if user_id is None else "WHERE user_id = %s"
            parameters = () if user_id is None else (user_id,)
            return list(
                connection.execute(
                    f"""
                    SELECT user_id, id, opportunity_id, title, status
                    FROM tasks
                    {where}
                    ORDER BY user_id, id
                    """,
                    parameters,
                ).fetchall()
            )

    def replace_task_scope(
        self,
        user_id: str,
        opportunity_id: str | None,
        titles: list[str],
        *,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        with self._connect() as connection:
            self._lock_user(connection, "tasks", user_id)
            counts = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                           WHERE opportunity_id IS NOT DISTINCT FROM %s
                       ) AS scoped
                FROM tasks
                WHERE user_id = %s
                """,
                (opportunity_id, user_id),
            ).fetchone()
            resulting_count = int(counts["total"]) - int(counts["scoped"]) + len(titles)
            if resulting_count > limit:
                return None
            next_id_row = connection.execute(
                """
                SELECT COALESCE(MAX(id), 0) + 1 AS next_id
                FROM tasks
                WHERE user_id = %s
                  AND opportunity_id IS DISTINCT FROM %s
                """,
                (user_id, opportunity_id),
            ).fetchone()
            next_id = int(next_id_row["next_id"])
            connection.execute(
                """
                DELETE FROM tasks
                WHERE user_id = %s
                  AND opportunity_id IS NOT DISTINCT FROM %s
                """,
                (user_id, opportunity_id),
            )
            generated: list[dict[str, Any]] = []
            for offset, title in enumerate(titles):
                record = {
                    "user_id": user_id,
                    "id": next_id + offset,
                    "opportunity_id": opportunity_id,
                    "title": title,
                    "status": "pending",
                }
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
                generated.append(record)
            return generated

    def update_task_status(
        self,
        user_id: str,
        task_id: int,
        task_status: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE tasks SET status = %s
                WHERE user_id = %s AND id = %s
                RETURNING user_id, id, opportunity_id, title, status
                """,
                (task_status, user_id, task_id),
            ).fetchone()

    def delete_task(self, user_id: str, task_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE user_id = %s AND id = %s",
                (user_id, task_id),
            )
            return cursor.rowcount == 1

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

    def load_profiles(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            where = "" if user_id is None else "WHERE user_id = %s"
            parameters = () if user_id is None else (user_id,)
            rows = connection.execute(
                f"""
                SELECT user_id, full_name, headline, location, summary,
                       education, work_experience, research_experience,
                       languages, skills, publications, updated_at
                FROM candidate_profiles
                {where}
                ORDER BY user_id
                """,
                parameters,
            ).fetchall()
        collection_fields = (
            "education",
            "work_experience",
            "research_experience",
            "languages",
            "skills",
            "publications",
        )
        return [
            {
                **row,
                **{
                    field: self._record_value(row[field])
                    for field in collection_fields
                },
            }
            for row in rows
        ]

    def upsert_profile(self, record: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO candidate_profiles (
                    user_id, full_name, headline, location, summary,
                    education, work_experience, research_experience,
                    languages, skills, publications, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    headline = EXCLUDED.headline,
                    location = EXCLUDED.location,
                    summary = EXCLUDED.summary,
                    education = EXCLUDED.education,
                    work_experience = EXCLUDED.work_experience,
                    research_experience = EXCLUDED.research_experience,
                    languages = EXCLUDED.languages,
                    skills = EXCLUDED.skills,
                    publications = EXCLUDED.publications,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    record["user_id"], record["full_name"], record["headline"],
                    record["location"], record["summary"],
                    self._json_param(record["education"]),
                    self._json_param(record["work_experience"]),
                    self._json_param(record["research_experience"]),
                    self._json_param(record["languages"]),
                    self._json_param(record["skills"]),
                    self._json_param(record["publications"]),
                    self._json_value(record["updated_at"]),
                ),
            )

    def delete_profile(self, user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM candidate_profiles WHERE user_id = %s",
                (user_id,),
            )
            return cursor.rowcount == 1

    def replace_profiles(
        self,
        records: Iterable[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        values = list(records)
        with self._connect() as connection:
            if user_id is None:
                connection.execute("DELETE FROM candidate_profiles")
            else:
                connection.execute(
                    "DELETE FROM candidate_profiles WHERE user_id = %s",
                    (user_id,),
                )
            for record in values:
                connection.execute(
                    """
                    INSERT INTO candidate_profiles (
                        user_id, full_name, headline, location, summary,
                        education, work_experience, research_experience,
                        languages, skills, publications, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["user_id"],
                        record["full_name"],
                        record["headline"],
                        record["location"],
                        record["summary"],
                        self._json_param(record["education"]),
                        self._json_param(record["work_experience"]),
                        self._json_param(record["research_experience"]),
                        self._json_param(record["languages"]),
                        self._json_param(record["skills"]),
                        self._json_param(record["publications"]),
                        self._json_value(record["updated_at"]),
                    ),
                )
