"""Resource-limit tests for the shared Playwright browser."""

from __future__ import annotations

import asyncio

import pytest

from app.browser import MAX_CONCURRENT_PAGES, BrowserManager


def test_run_with_page_limits_concurrent_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BrowserManager()
    assert manager._page_slots._value == MAX_CONCURRENT_PAGES

    active = 0
    peak = 0

    async def fake_with_page(_action: object) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "ok"

    async def fake_dispatch(coro: asyncio.Future[str]) -> str:
        return await coro

    monkeypatch.setattr(manager, "_with_page", fake_with_page)
    monkeypatch.setattr(manager, "_dispatch", fake_dispatch)

    async def run() -> list[str]:
        return await asyncio.gather(
            *(manager.run_with_page(lambda page: None) for _ in range(10))
        )

    assert all(result == "ok" for result in asyncio.run(run()))
    assert peak <= MAX_CONCURRENT_PAGES
