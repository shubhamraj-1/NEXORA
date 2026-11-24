"""Shared authenticated fixtures for the NEXORA API tests.

These fixtures keep authentication enabled and exercise real JWT verification.
They only redirect the app to isolated test settings for the duration of each
test; production ``.env`` values, Supabase data, and RLS are never modified.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace

import jwt
import pytest
from fastapi.testclient import TestClient

from app import agent as agent_module
from app import auth as auth_module
from app import supabase_store as store_module
from app.config import settings
from app.main import app
from app.ratelimit import rate_limiter

TEST_SECRET = "test-only-local-secret"
TEST_ISSUER = "https://example.supabase.co/auth/v1"
TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


def _test_settings():
    """Isolated settings with auth ON but no external writes."""
    return replace(
        settings,
        supabase_url="https://example.supabase.co",
        supabase_jwks_url="",
        supabase_jwt_secret=TEST_SECRET,
        supabase_service_role_key="",
        database_configured=False,
    )


def _access_token() -> str:
    return jwt.encode(
        {
            "sub": TEST_USER_ID,
            "email": "tester@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": TEST_ISSUER,
            "exp": int(time.time()) + 3600,
        },
        TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def authenticated_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch module-level settings in-process; restore automatically."""
    configured = _test_settings()
    for module in (auth_module, agent_module, store_module):
        monkeypatch.setattr(module, "settings", configured)


@pytest.fixture(autouse=True)
def clean_rate_limiter() -> Iterator[None]:
    """Keep tests independent of the global sliding window."""
    rate_limiter.clear()
    yield
    rate_limiter.clear()


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """One authenticated client so Chromium starts only once."""
    with TestClient(app, headers={"Authorization": f"Bearer {_access_token()}"}) as test_client:
        yield test_client
