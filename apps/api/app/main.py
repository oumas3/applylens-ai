from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class ProductInfo(BaseModel):
    name: str
    phase: str
    supported_opportunities: list[str]
    promise: str


app = FastAPI(
    title="ApplyLens AI API",
    version="0.1.0",
    description="Evidence-based application intelligence for Master's and PhD candidates.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "applylens-api"}


@app.get("/api/v1/product", response_model=ProductInfo)
def product() -> ProductInfo:
    return ProductInfo(
        name="ApplyLens AI",
       phase="Sprint 0 \u2014 Foundation",
        supported_opportunities=["Master's", "PhD"],
        promise="Every decision is backed by evidence or marked unclear.",
    )

