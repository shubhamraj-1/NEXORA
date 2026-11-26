"""API tests for NEXORA. Run from the repo root: ``python -m pytest backend/tests -q``."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app import agent as agent_module
from app import auth as auth_module
from app import security as security_module
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


def _scraped_page() -> dict[str, Any]:
    """Browser-manager payload matching _scrape's successful result."""
    return {
        "final_url": "https://example.com/",
        "status_code": 200,
        "title": "Example Domain",
        "description": "",
        "text": "Example Domain",
        "headings": [],
        "raw_links": [],
        "screenshot_base64": None,
    }


def _enable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = replace(
        settings,
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret="local-only-test-secret-not-for-production-32b",
    )
    monkeypatch.setattr(auth_module, "settings", configured)
    monkeypatch.setattr(agent_module, "settings", configured)


def _token(
    *,
    subject: str | None = "user-123",
    issuer: str | None = None,
    audience: str = "authenticated",
) -> str:
    """Mint a local HS256 token for authorization tests."""
    secret = auth_module.settings.supabase_jwt_secret
    claims: dict[str, object] = {
        "email": "tester@example.com",
        "role": "authenticated",
        "aud": audience,
        "iss": issuer or f"{auth_module.settings.supabase_url}/auth/v1",
        "exp": int(time.time()) + 300,
    }
    if subject is not None:
        claims["sub"] = subject
    return jwt.encode(claims, secret, algorithm="HS256")


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
    assert body["browser"]["max_attempts"] == agent_module.MAX_BROWSER_ATTEMPTS
    assert body["limits"]["max_timeout_ms"] == 120_000
    assert "auth" in body and "ai" in body


def test_invalid_url_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/agent/run", json={"url": "not-a-url", "instruction": "x"}
    )
    assert response.status_code == 422


def test_private_dns_answer_is_rejected_off_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DNS validation still blocks a public-looking host resolving privately."""

    def private_answer(*_: object, **__: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(security_module.socket, "getaddrinfo", private_answer)
    response = client.post(
        "/v1/agent/run", json={"url": "https://public.example", "instruction": "x"}
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


def test_agent_run_retries_transient_timeout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def flaky(_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PlaywrightTimeoutError("Timeout 1000ms exceeded")
        return _scraped_page()

    monkeypatch.setattr(agent_module.browser_manager, "run_with_page", flaky)
    monkeypatch.setattr(agent_module, "BROWSER_RETRY_DELAY_S", 0)

    response = client.post(
        "/v1/agent/run",
        json={"url": "https://example.com", "instruction": "x", "ai": False},
    )

    assert response.status_code == 200
    assert calls == 2
    actions = [step["action"] for step in response.json()["steps"]]
    assert "retry" in actions
    assert actions.count("retry") == 1


def test_agent_run_does_not_retry_non_transient_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def fail(_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise PlaywrightError("unsupported scheme")

    monkeypatch.setattr(agent_module.browser_manager, "run_with_page", fail)

    response = client.post(
        "/v1/agent/run",
        json={"url": "https://example.com", "instruction": "x", "ai": False},
    )

    assert response.status_code == 502
    assert calls == 1


def test_agent_run_timeout_fails_after_bounded_attempts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def always_timeout(_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise PlaywrightTimeoutError("Timeout 1000ms exceeded")

    monkeypatch.setattr(agent_module.browser_manager, "run_with_page", always_timeout)
    monkeypatch.setattr(agent_module, "BROWSER_RETRY_DELAY_S", 0)

    response = client.post(
        "/v1/agent/run",
        json={"url": "https://example.com", "instruction": "x", "ai": False},
    )

    assert response.status_code == 504
    assert calls == agent_module.MAX_BROWSER_ATTEMPTS


def test_task_logs_retry_when_browser_recovers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def flaky(_: object) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PlaywrightError("net::ERR_CONNECTION_RESET")
        return _scraped_page()

    monkeypatch.setattr(agent_module.browser_manager, "run_with_page", flaky)
    monkeypatch.setattr(agent_module, "BROWSER_RETRY_DELAY_S", 0)

    created = client.post(
        "/v1/tasks",
        json={"url": "https://example.com", "instruction": "x", "ai": False},
    )
    assert created.status_code == 202
    task_id = created.json()["id"]

    record = _wait_for_status(client, task_id, "succeeded")
    assert record["progress"] == 100
    logs = client.get(f"/v1/tasks/{task_id}/logs").json()
    assert any("retry" in entry["message"].lower() for entry in logs)
    assert client.get(f"/v1/tasks/{task_id}/result").status_code == 200
    assert calls == 2


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


def test_auth_rejects_expired_token(client: TestClient) -> None:
    secret = auth_module.settings.supabase_jwt_secret
    token = jwt.encode(
        {
            "sub": "user-123",
            "email": "tester@example.com",
            "aud": "authenticated",
            "iss": f"{auth_module.settings.supabase_url}/auth/v1",
            "exp": int(time.time()) - 10,
        },
        secret,
        algorithm="HS256",
    )
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"url": "https://example.com"},
    )
    assert response.status_code == 401


def test_auth_rejects_wrong_issuer(client: TestClient) -> None:
    response = client.get(
        "/v1/tasks",
        headers={"Authorization": f"Bearer {_token(issuer='https://evil.example/auth/v1')}"},
    )
    assert response.status_code == 401


def test_auth_rejects_wrong_audience(client: TestClient) -> None:
    response = client.get(
        "/v1/tasks",
        headers={"Authorization": f"Bearer {_token(audience='anon')}"},
    )
    assert response.status_code == 401


def test_auth_rejects_token_without_subject(client: TestClient) -> None:
    response = client.get(
        "/v1/tasks",
        headers={"Authorization": f"Bearer {_token(subject=None)}"},
    )
    assert response.status_code == 401


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
    assert response.json()["detail"] == "Invalid or expired access token."
    assert "bad token" not in response.json()["detail"]


def test_private_and_metadata_urls_are_rejected(client: TestClient) -> None:
    for url in ("http://127.0.0.1", "http://localhost", "http://metadata.google.internal"):
        response = client.post(
            "/v1/agent/run", json={"url": url, "instruction": "x"}
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    "url",
    [
        "http://100.64.0.1",  # shared/CGNAT range
        "http://198.18.0.1",  # benchmarking range
        "http://0.0.0.0",
        "http://[::ffff:127.0.0.1]",
    ],
)
def test_non_global_ip_literals_are_rejected(client: TestClient, url: str) -> None:
    response = client.post("/v1/agent/run", json={"url": url, "instruction": "x"})
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
    client: TestClient,
    task_id: str,
    expected: str,
    timeout_s: float = 5.0,
    token: str | None = None,
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"} if token else None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/v1/tasks/{task_id}", headers=headers).json()
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


def test_tasks_are_isolated_between_users(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def instant(_: object) -> AgentRunResponse:
        return _result()

    monkeypatch.setattr(tasks_module, "execute_run", instant)

    owner_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    owner_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    token_a = _token(subject=owner_a)
    token_b = _token(subject=owner_b)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    created = client.post(
        "/v1/tasks",
        headers=headers_a,
        json={"url": "https://example.com"},
    )
    assert created.status_code == 202
    task_id = created.json()["id"]
    _wait_for_status(client, task_id, "succeeded", token=token_a)

    assert client.get(f"/v1/tasks/{task_id}", headers=headers_a).status_code == 200
    assert client.get(f"/v1/tasks/{task_id}", headers=headers_b).status_code == 404
    assert client.get(f"/v1/tasks/{task_id}/logs", headers=headers_b).status_code == 404
    assert client.get(f"/v1/tasks/{task_id}/result", headers=headers_b).status_code == 404
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers_b).status_code == 404

    list_b = client.get("/v1/tasks", headers=headers_b)
    assert list_b.status_code == 200
    assert all(item["id"] != task_id for item in list_b.json())


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
    secret = "another-local-test-secret-not-for-production-32b"
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
