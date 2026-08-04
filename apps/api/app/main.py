from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from typing import Literal
from app.routers.documents import router as documents_router
from app.routers.opportunities import router as opportunities_router
from app.routers.tasks import router as tasks_router
from app.routers.reviews import router as reviews_router
from app.routers.auth import router as auth_router
from app.config import get_settings


class ProductInfo(BaseModel):
    name: str
    phase: str
    supported_opportunities: list[str]
    promise: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str
    checks: dict[str, str]


settings = get_settings()

app = FastAPI(
    title="ApplyLens AI API",
    version="0.1.0",
    description=(
        "Evidence-based application intelligence for "
        "Master's and PhD candidates."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.web_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)
app.include_router(opportunities_router)
app.include_router(tasks_router)
app.include_router(reviews_router)
app.include_router(auth_router)

@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "applylens-api",
        "environment": settings.app_env,
    }


@app.get("/health/ready", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse | JSONResponse:
    """Report whether configured runtime dependencies can serve requests."""
    checks = {"api": "ok"}

    if settings.retrieval_storage == "pgvector":
        try:
            import psycopg

            with psycopg.connect(settings.database_url, connect_timeout=3) as connection:
                connection.execute("SELECT 1 FROM opportunity_chunks LIMIT 1")
        except Exception:
            checks["pgvector"] = "error"
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "service": "applylens-api",
                    "checks": checks,
                },
            )
        checks["pgvector"] = "ok"
    else:
        checks["retrieval"] = "ok"

    return ReadinessResponse(
        status="ready",
        service="applylens-api",
        checks=checks,
    )


@app.get("/api/v1/product", response_model=ProductInfo)
def product() -> ProductInfo:
    return ProductInfo(
        name="ApplyLens AI",
        phase="Sprint 5 — Production hardening",
        supported_opportunities=["Master's", "PhD"],
        promise="Every decision is backed by evidence or marked unclear.",
    )
