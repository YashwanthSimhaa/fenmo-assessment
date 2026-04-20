"""
Expense Tracker API — main application entrypoint.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.database import init_db
from src.routes.expenses import router as expenses_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB tables on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Expense Tracker API",
    description="A minimal, production-grade personal expense tracker.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the frontend (any origin in dev; tighten in prod via env var)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(expenses_router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
