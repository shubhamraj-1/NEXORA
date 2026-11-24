"""API tests for NEXORA. Run from ``backend/``: ``python -m pytest -q``."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import jwt
import pytest
from fastapi.testclient import TestClient

from app import agent as agent_module
from app import auth as auth_module
from app import tasks as tasks_module
from app.config import settings
from app.ratelimit import rate_limiter
from app.schemas import AgentRunResponse


def _result() -> AgentRunResponse:
    return AgentRunResponse(
        url="https://example.com",
        final_url="https://example.com/",
        title="Example Domain",
        description="",
        status_code=200,
        instruction="What is this page?",
        text="Example Domain",
        text_truncated=False,
        headings=[],
        links=[],
        screenshot_base64=None,
        steps=[{"action": "navigate", "detail": "GET https://example.com", "duration_ms": 1}],
        elapsed_ms=1,
    )


def _enable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = replace(
        settings,
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret="test-secret",
    )
    monkeypatch.setattr(auth_module, "settings", configured)
    monkeypatch.setattr(agent_module, "settings", configured)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nexora-api"}


def test_model_list(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert [item["id"] for item in body["data"]] == ["nexora-web-intelligence"]


def test_capabilities(client: TestClient) -> None:
    response = client.get("/v1/agent/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["browser"]["engine"] == "chromium"
    assert body["limits"]["max_timeout_ms"] == 120_000
    assert "auth" in body and "ai" in body


def test_invalid_url_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/agent/run", json={"url": "not-a-url", "instruction": "x"}
    )
    assert response.status_code == 422


def test_agent_run_extracts_example_page(client: TestClient) -> None:
    response = client.post(
        "/v1/agent/run",
        json={
            "url": "https://example.com",
            "instruction": "What is this page?",
            "ai": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "Example" in body["title"]
    assert body["status_code"] == 200
    assert body["steps"][0]["action"] == "navigate"
    assert body["answer"] is None
    assert body["plan"] == []


def test_auth_required_when_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_auth(monkeypatch)
    monkeypatch.setattr(
        auth_module,
        "verify_access_token",
        lambda token: {"sub": "user-123", "email": "tester@example.com"},
    )

    capabilities = client.get("/v1/agent/capabilities").json()
    assert capabilities["auth"]["required"] is True
    assert capabilities["auth"]["provider"] == "supabase"

    anonymous = client.post(
        "/v1/agent/run",
        headers={"Authorization": ""},
        json={"url": "https://example.com", "instruction": "x"},
    )
    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"] == "Bearer"

    authorized = client.post(
        "/v1/agent/run",
        headers={"Authorization": "Bearer valid-supabase-token"},
        json={"url": "not-a-url"},
    )
    assert authorized.status_code == 422


def test_auth_rejects_invalid_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_auth(monkeypatch)

    def reject(_: str) -> dict[str, str]:
        raise ValueError("bad token")

    monkeypatch.setattr(auth_module, "verify_access_token", reject)

    response = client.post(
        "/v1/agent/run",
        headers={"Authorization": "Bearer broken-token"},
        json={"url": "https://example.com", "instruction": "x"},
    )
    assert response.status_code == 401
    assert "bad token" in response.json()["detail"]


def test_private_and_metadata_urls_are_rejected(client: TestClient) -> None:
    for url in ("http://127.0.0.1", "http://localhost", "http://metadata.google.internal"):
        response = client.post(
            "/v1/agent/run", json={"url": url, "instruction": "x"}
        )
        assert response.status_code == 422


def test_capabilities_expose_task_and_rate_limit_info(client: TestClient) -> None:
    body = client.get("/v1/agent/capabilities").json()
    assert body["tasks"]["enabled"] is True
    assert "cancelled" in body["tasks"]["statuses"]
    assert body["limits"]["rate_limit_per_minute"] >= 1


def test_rate_limit_returns_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limiter, "limit", 1)

    async def instant(_: object) -> AgentRunResponse:
        return _result()

    monkeypatch.setattr(tasks_module, "execute_run", instant)

    first = client.post("/v1/tasks", json={"url": "https://example.com"})
    second = client.post("/v1/tasks", json={"url": "https://example.com"})

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["retry-after"]


def _wait_for_status(
    client: TestClient, task_id: str, expected: str, timeout_s: float = 5.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/v1/tasks/{task_id}").json()
        if body.get("status") == expected:
            return body
        time.sleep(0.05)
    pytest.fail(f"Task {task_id} never reached {expected}")


def test_task_result_and_logs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def instant(_: object) -> AgentRunResponse:
        return _result()

    monkeypatch.setattr(tasks_module, "execute_run", instant)

    created = client.post("/v1/tasks", json={"url": "https://example.com"})
    assert created.status_code == 202
    task_id = created.json()["id"]

    record = _wait_for_status(client, task_id, "succeeded")
    assert record["progress"] == 100

    result = client.get(f"/v1/tasks/{task_id}/result")
    assert result.status_code == 200
    assert result.json()["title"] == "Example Domain"

    logs = client.get(f"/v1/tasks/{task_id}/logs").json()
    assert any(entry["message"] == "Task completed." for entry in logs)


def test_task_can_be_cancelled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def slow(_: object) -> AgentRunResponse:
        await asyncio.sleep(2)
        return _result()

    monkeypatch.setattr(tasks_module, "execute_run", slow)

    created = client.post("/v1/tasks", json={"url": "https://example.com"})
    task_id = created.json()["id"]
    _wait_for_status(client, task_id, "running")

    cancelled = client.delete(f"/v1/tasks/{task_id}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    time.sleep(0.1)
    logs = client.get(f"/v1/tasks/{task_id}/logs").json()
    assert any("cancel" in entry["message"].lower() for entry in logs)


def test_supabase_jwt_is_verified_with_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "a-real-test-secret"
    monkeypatch.setattr(
        auth_module,
        "settings",
        replace(
            settings,
            supabase_url="https://example.supabase.co",
            supabase_jwt_secret=secret,
        ),
    )
    token = jwt.encode(
        {
            "sub": "user-123",
            "email": "tester@example.com",
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )
    claims = auth_module.verify_access_token(token)
    assert claims["sub"] == "user-123"
    assert claims["email"] == "tester@example.com"
