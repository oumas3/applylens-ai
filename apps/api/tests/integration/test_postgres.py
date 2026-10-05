import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest

from app.migrations import discover_migrations, run_migrations
from app.services.application_store import PostgresApplicationStore
from app.services.retrieval_service import PgVectorRetriever, TextChunk


DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


class FixedEmbeddingProvider:
    dimension = 1536

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        vector[0 if "degree" in text.lower() else 1] = 1.0
        return vector

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


def test_migrations_are_applied_once_and_schema_is_ready() -> None:
    assert DATABASE_URL is not None

    first_run = run_migrations(DATABASE_URL)
    second_run = run_migrations(DATABASE_URL)

    assert set(first_run) <= {
        migration.filename for migration in discover_migrations()
    }
    assert second_run == []
    PostgresApplicationStore(DATABASE_URL).check()

    with psycopg.connect(DATABASE_URL) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
    assert count == len(discover_migrations())


def test_pgvector_search_is_scoped_to_the_selected_opportunity() -> None:
    assert DATABASE_URL is not None
    provider = FixedEmbeddingProvider()
    first_id = f"integration-{uuid4()}"
    second_id = f"integration-{uuid4()}"
    first = PgVectorRetriever(DATABASE_URL, provider, first_id)
    second = PgVectorRetriever(DATABASE_URL, provider, second_id)

    first.index(
        [
            TextChunk(
                chunk_id=f"chunk-{uuid4()}",
                text="A degree is required.",
                source_name="first.txt",
                index=0,
            )
        ]
    )
    second.index(
        [
            TextChunk(
                chunk_id=f"chunk-{uuid4()}",
                text="A degree from the other call.",
                source_name="second.txt",
                index=0,
            )
        ]
    )

    results = first.search("degree", top_k=5)

    assert [result.chunk.source_name for result in results] == ["first.txt"]


def test_application_store_crud_is_tenant_scoped_and_request_fresh() -> None:
    assert DATABASE_URL is not None
    run_migrations(DATABASE_URL)
    first_user = f"integration-user-{uuid4()}"
    second_user = f"integration-user-{uuid4()}"
    now = datetime.now(timezone.utc)

    with psycopg.connect(DATABASE_URL) as connection:
        for user_id in (first_user, second_user):
            connection.execute(
                """
                INSERT INTO users (id, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (user_id, f"{user_id}@example.com", "integration-test-hash"),
            )

    first_store = PostgresApplicationStore(DATABASE_URL)
    second_store = PostgresApplicationStore(DATABASE_URL)
    first_document_id = f"document-{uuid4()}"
    second_document_id = f"document-{uuid4()}"
    opportunity_id = f"opportunity-{uuid4()}"

    try:
        assert first_store.create_document(
            {
                "id": first_document_id,
                "user_id": first_user,
                "original_filename": "first.txt",
                "stored_filename": "first.txt",
                "category": "CV",
                "content_type": "text/plain",
                "size_bytes": 14,
                "status": "uploaded",
                "extracted_text_length": 14,
                "extracted_text": "first evidence",
                "extracted_pages": [{"number": None, "text": "first evidence"}],
                "uploaded_at": now,
            },
            limit=1,
        ) is True
        assert first_store.create_document(
            {
                "id": f"document-{uuid4()}",
                "user_id": first_user,
                "original_filename": "over-limit.txt",
                "stored_filename": "over-limit.txt",
                "category": "OTHER",
                "content_type": "text/plain",
                "size_bytes": 1,
                "status": "uploaded",
                "extracted_text_length": 1,
                "extracted_text": "x",
                "extracted_pages": [],
                "uploaded_at": now,
            },
            limit=1,
        ) is False
        assert second_store.create_document(
            {
                "id": second_document_id,
                "user_id": second_user,
                "original_filename": "second.txt",
                "stored_filename": "second.txt",
                "category": "CV",
                "content_type": "text/plain",
                "size_bytes": 15,
                "status": "uploaded",
                "extracted_text_length": 15,
                "extracted_text": "second evidence",
                "extracted_pages": [],
                "uploaded_at": now,
            },
            limit=1,
        ) is True

        assert [item["id"] for item in second_store.load_documents(first_user)] == [
            first_document_id
        ]
        assert [item["id"] for item in first_store.load_documents(second_user)] == [
            second_document_id
        ]

        assert first_store.create_opportunity(
            {
                "id": opportunity_id,
                "user_id": first_user,
                "title": "Integration PhD",
                "source_text": "Applicants must provide a degree.",
                "institution": "Example University",
                "degree_type": "PhD",
                "source_name": "call.txt",
                "source_url": None,
                "requirements": ["Applicants must provide a degree."],
                "requirement_citations": [],
                "deadline": None,
                "deadline_date": None,
                "funding": None,
            },
            limit=1,
        ) is True
        assert second_store.load_opportunities(first_user)[0]["id"] == opportunity_id

        review_record = {
            "user_id": first_user,
            "id": 1,
            "title": "Integration review",
            "eligibility": "Insufficient information",
            "matched_requirements": [],
            "missing_requirements": ["Degree"],
            "deadline": None,
            "funding": None,
        }
        assert first_store.create_review(review_record, limit=1) == "created"
        assert second_store.create_review(review_record, limit=1) == "duplicate"

        generated = first_store.replace_task_scope(
            first_user,
            opportunity_id,
            ["Provide degree evidence", "Confirm deadline"],
            limit=2,
        )
        assert generated is not None
        assert len(second_store.load_tasks(first_user)) == 2
        assert first_store.replace_task_scope(
            first_user,
            None,
            ["one extra task"],
            limit=2,
        ) is None

        first_store.upsert_profile(
            {
                "user_id": first_user,
                "full_name": "Integration Candidate",
                "headline": None,
                "location": None,
                "summary": None,
                "education": [],
                "work_experience": [],
                "research_experience": [],
                "languages": [],
                "skills": [],
                "publications": [],
                "updated_at": now,
            }
        )
        assert second_store.load_profiles(first_user)[0]["full_name"] == (
            "Integration Candidate"
        )

        assert first_store.delete_review(first_user, 1) is True
        assert first_store.delete_opportunity(first_user, opportunity_id) is True
        assert first_store.delete_document(first_user, first_document_id) is True
        assert second_store.load_documents(first_user) == []
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM users WHERE id = ANY(%s)",
                ([first_user, second_user],),
            )
