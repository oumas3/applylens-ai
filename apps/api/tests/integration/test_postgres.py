import os
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
