from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.routers.documents import router as documents_router
from app.config import get_settings


class ProductInfo(BaseModel):
    name: str
    phase: str
    supported_opportunities: list[str]
    promise: str


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

@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "applylens-api",
        "environment": settings.app_env,
    }


@app.get("/api/v1/product", response_model=ProductInfo)
def product() -> ProductInfo:
    return ProductInfo(
        name="ApplyLens AI",
        phase="Sprint 0 — Foundation",
        supported_opportunities=["Master's", "PhD"],
        promise="Every decision is backed by evidence or marked unclear.",
    )