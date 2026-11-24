"""Environment-driven configuration for the NEXORA backend.

Values come from real environment variables first, then from a ``.env`` file at
the repository root (or in ``backend/``). Nothing is required: with no keys the
API runs in deterministic local mode. Supabase becomes active when its URL and
JWT verification settings are present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

load_dotenv(PROJECT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration resolved once at import time."""

    openai_api_key: str | None
    openai_model: str
    openai_timeout_s: float
    max_ai_context_chars: int
    ai_max_plan_steps: int

    supabase_url: str | None
    supabase_anon_key: str | None
    supabase_service_role_key: str | None
    supabase_jwt_secret: str | None
    supabase_jwks_url: str | None
    supabase_storage_bucket: str
    database_configured: bool

    rate_limit_per_minute: int
    rate_limit_window_seconds: int

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def auth_required(self) -> bool:
        """Verification requires a project URL plus a secret or JWKS endpoint."""
        return bool(
            self.supabase_url
            and (self.supabase_jwt_secret or self.supabase_jwks_url)
        )

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _jwks_url(url: str | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if not url:
        return None
    return f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json"


settings = Settings(
    openai_api_key=_clean(os.getenv("OPENAI_API_KEY")),
    openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    openai_timeout_s=_float("OPENAI_TIMEOUT_S", 30.0),
    max_ai_context_chars=_int("MAX_AI_CONTEXT_CHARS", 6000),
    ai_max_plan_steps=_int("AI_MAX_PLAN_STEPS", 8),
    supabase_url=_clean(os.getenv("SUPABASE_URL")),
    supabase_anon_key=_clean(os.getenv("SUPABASE_ANON_KEY")),
    supabase_service_role_key=_clean(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
    supabase_jwt_secret=_clean(os.getenv("SUPABASE_JWT_SECRET")),
    supabase_jwks_url=_clean(os.getenv("SUPABASE_JWKS_URL")),
    supabase_storage_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "generated-files"),
    database_configured=_bool("DATABASE_CONFIGURED"),
    rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 30),
    rate_limit_window_seconds=_int("RATE_LIMIT_WINDOW_SECONDS", 60),
)
