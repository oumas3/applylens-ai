import asyncio

import pytest
from pydantic import ValidationError

from app.routers.opportunities import (
    OpportunityAnalysisRequest,
    OpportunityIngestRequest,
)
from app.routers.reviews import OpportunityReview
from app.routers.tasks import TaskGenerationRequest
from app.security import RequestBodyLimitMiddleware


def test_opportunity_models_reject_oversized_text_and_collections() -> None:
    with pytest.raises(ValidationError):
        OpportunityIngestRequest(title="Example", source_text="x" * 500_001)

    with pytest.raises(ValidationError):
        OpportunityAnalysisRequest(
            title="Example",
            requirements=["requirement"] * 101,
        )

    with pytest.raises(ValidationError):
        OpportunityAnalysisRequest(
            title="Example",
            evidence=["x" * 10_001],
        )


def test_review_and_task_models_reject_oversized_content() -> None:
    with pytest.raises(ValidationError):
        OpportunityReview(
            id=1,
            title="x" * 301,
            eligibility="Insufficient information",
        )

    with pytest.raises(ValidationError):
        TaskGenerationRequest(missing_requirements=["item"] * 101)


def test_request_body_limit_rejects_declared_oversize_before_endpoint() -> None:
    endpoint_called = False
    sent: list[dict] = []

    async def endpoint(scope, receive, send) -> None:
        nonlocal endpoint_called
        endpoint_called = True

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(endpoint, max_bytes=10)
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "headers": [(b"content-length", b"11")],
            },
            receive,
            send,
        )
    )

    assert endpoint_called is False
    assert sent[0]["status"] == 413


def test_request_body_limit_counts_streamed_bytes_without_content_length() -> None:
    sent: list[dict] = []
    chunks = iter(
        [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"78901", "more_body": False},
        ]
    )

    async def endpoint(scope, receive, send) -> None:
        await receive()
        await receive()

    async def receive() -> dict:
        return next(chunks)

    async def send(message: dict) -> None:
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(endpoint, max_bytes=10)
    asyncio.run(
        middleware(
            {"type": "http", "method": "POST", "headers": []},
            receive,
            send,
        )
    )

    assert sent[0]["status"] == 413
