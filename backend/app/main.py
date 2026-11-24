"""FastAPI application entry point for NEXORA."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import router as agent_router
from .browser import browser_manager
from .tasks import router as tasks_router, task_manager

# Timestamp used for the static model catalogue (2025-01-01T00:00:00Z).
_MODEL_CREATED_AT = 1735689600


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start Chromium with the API and shut it down cleanly afterwards."""
    await browser_manager.start()
    try:
        yield
    finally:
        await task_manager.shutdown()
        await browser_manager.stop()


app = FastAPI(
    title="NEXORA API",
    description=(
        "Backend API for the NEXORA autonomous web intelligence platform: "
        "Playwright browsing, structured extraction and optional OpenAI planning."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(agent_router)
app.include_router(tasks_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ModelCard(BaseModel):
    """A single model entry in the OpenAI-compatible model list."""

    id: str
    object: str = "model"
    created: int = _MODEL_CREATED_AT
    owned_by: str = "nexora"


class ModelList(BaseModel):
    """Response body for the OpenAI-compatible model listing."""

    object: str = "list"
    data: list[ModelCard]


AVAILABLE_MODELS: list[ModelCard] = [
    ModelCard(id="nexora-web-intelligence"),
]


@app.get("/", tags=["service"])
async def read_root() -> dict[str, str]:
    """Describe the service and point at the useful entry points."""
    return {
        "service": "nexora-api",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "models": "/v1/models",
        "agent": "/v1/agent/run",
        "tasks": "/v1/tasks",
        "capabilities": "/v1/agent/capabilities",
    }


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Report whether the API process is responding."""
    return {"status": "ok", "service": "nexora-api"}


@app.get("/v1/models", tags=["models"], response_model=ModelList)
async def list_models() -> ModelList:
    """List the models exposed through NEXORA's OpenAI-compatible API."""
    return ModelList(data=AVAILABLE_MODELS)
