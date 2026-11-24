"""The NEXORA agent: navigate a page, extract structure, trace every step."""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .browser import BrowserUnavailableError, browser_manager
from .config import settings
from .planner import ai_available, plan_run
from .ratelimit import rate_limited_user
from .schemas import AgentRunRequest, AgentRunResponse, AgentStep, ExtractedLink
from .security import validate_public_url

router = APIRouter(prefix="/v1/agent", tags=["agent"])

MAX_TEXT_CHARS = 20_000
MAX_HEADINGS = 20
MAX_SCREENSHOT_BYTES = 5_000_000
NETWORK_IDLE_BUDGET_MS = 5_000

_LINK_HINTS = ("link", "url", "href", "reference")
_SCREENSHOT_HINTS = ("screenshot", "capture", "image", "picture", "snapshot")

# Runs inside the page. Slicing bounds the payload before it leaves the browser;
# Python applies the real limits afterwards.
_EXTRACT_SCRIPT = """
() => {
  const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
  const root = document.querySelector("main, article, [role=main]") || document.body;
  const anchors = Array.from(document.querySelectorAll("a[href]"));
  return {
    title: clean(document.title),
    description: clean(
      document.querySelector('meta[name="description"]')?.getAttribute("content")
    ),
    text: clean(root ? root.innerText : ""),
    headings: Array.from(document.querySelectorAll("h1, h2, h3"))
      .map((node) => clean(node.innerText))
      .filter((value) => value.length > 0)
      .slice(0, 50),
    links: anchors
      .map((anchor) => ({
        text: clean(anchor.innerText) || clean(anchor.getAttribute("aria-label")),
        href: anchor.href,
      }))
      .filter((link) => link.href.startsWith("http"))
      .slice(0, 500),
  };
}
"""


def _record(
    steps: list[AgentStep], action: str, detail: str, phase_started: float
) -> None:
    """Append a step describing a phase that just finished."""
    steps.append(
        AgentStep(
            action=action,
            detail=detail,
            duration_ms=int((time.perf_counter() - phase_started) * 1000),
        )
    )


def _wants_screenshot(request: AgentRunRequest) -> bool:
    if request.include_screenshot:
        return True
    lowered = request.instruction.lower()
    return any(hint in lowered for hint in _SCREENSHOT_HINTS)


def _link_limit(request: AgentRunRequest) -> int:
    """Widen link extraction when the instruction explicitly asks for links."""
    if request.max_links == 0:
        return 0
    lowered = request.instruction.lower()
    if any(hint in lowered for hint in _LINK_HINTS):
        return max(request.max_links, 50)
    return request.max_links


def _dedupe_links(raw: list[dict[str, Any]], limit: int) -> list[ExtractedLink]:
    if limit <= 0:
        return []
    seen: set[str] = set()
    links: list[ExtractedLink] = []
    for item in raw:
        href = str(item.get("href") or "")
        if not href or href in seen:
            continue
        seen.add(href)
        links.append(ExtractedLink(text=str(item.get("text") or ""), href=href))
        if len(links) >= limit:
            break
    return links


async def _guard_navigation(route: Any) -> None:
    """Abort document navigations that leave the public web (redirect SSRF)."""
    if route.request.resource_type == "document":
        try:
            await asyncio.to_thread(validate_public_url, route.request.url)
        except ValueError:
            await route.abort()
            return
    await route.continue_()


async def _scrape(
    page: Page, request: AgentRunRequest, steps: list[AgentStep]
) -> dict[str, Any]:
    """Drive one page. Runs on the Playwright worker loop, not the request loop."""
    target_url = str(request.url)
    await page.route("**/*", _guard_navigation)

    phase = time.perf_counter()
    response = await page.goto(
        target_url,
        wait_until="domcontentloaded",
        timeout=request.timeout_ms,
    )
    status_code = response.status if response is not None else None
    _record(steps, "navigate", f"GET {target_url} (domcontentloaded)", phase)

    phase = time.perf_counter()
    try:
        await page.wait_for_load_state(
            "networkidle", timeout=min(request.timeout_ms, NETWORK_IDLE_BUDGET_MS)
        )
        settle_detail = "network idle reached"
    except PlaywrightTimeoutError:
        # Busy pages (analytics, chat widgets) rarely go idle; carry on.
        settle_detail = (
            f"network idle not reached within {NETWORK_IDLE_BUDGET_MS} ms; continuing"
        )
    _record(steps, "settle", settle_detail, phase)

    phase = time.perf_counter()
    raw = await page.evaluate(_EXTRACT_SCRIPT) or {}
    _record(steps, "extract", "read text, headings and links", phase)

    screenshot_b64: str | None = None
    if _wants_screenshot(request):
        phase = time.perf_counter()
        png = await page.screenshot(full_page=True)
        if len(png) > MAX_SCREENSHOT_BYTES:
            detail = f"skipped {len(png)} byte PNG (limit {MAX_SCREENSHOT_BYTES} bytes)"
        else:
            screenshot_b64 = base64.b64encode(png).decode("ascii")
            detail = f"captured {len(png)} byte PNG"
        _record(steps, "screenshot", detail, phase)

    return {
        "final_url": page.url,
        "status_code": status_code,
        "title": str(raw.get("title") or ""),
        "description": str(raw.get("description") or ""),
        "text": str(raw.get("text") or ""),
        "headings": [str(item) for item in raw.get("headings") or []][
            :MAX_HEADINGS
        ],
        "raw_links": raw.get("links") or [],
        "screenshot_base64": screenshot_b64,
    }


async def execute_run(request: AgentRunRequest) -> AgentRunResponse:
    """Execute one run. Shared by the synchronous route and the task worker."""
    started = time.perf_counter()
    steps: list[AgentStep] = []
    try:
        target_url = await asyncio.to_thread(validate_public_url, request.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    try:
        scraped = await browser_manager.run_with_page(
            lambda page: _scrape(page, request, steps)
        )
    except PlaywrightTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Timed out after {request.timeout_ms} ms while visiting {target_url}.",
        ) from exc
    except PlaywrightError as exc:
        message = getattr(exc, "message", str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Browser failed while visiting {target_url}: {message}",
        ) from exc
    except BrowserUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    full_text = scraped["text"]
    text_truncated = len(full_text) > MAX_TEXT_CHARS
    links = _dedupe_links(scraped["raw_links"], _link_limit(request))

    plan: list[str] = []
    answer: str | None = None
    model: str | None = None
    if request.ai and ai_available():
        phase = time.perf_counter()
        planned = await plan_run(
            instruction=request.instruction,
            url=scraped["final_url"],
            title=scraped["title"],
            text=full_text[:MAX_TEXT_CHARS],
            links=links,
        )
        if planned is None:
            _record(
                steps,
                "plan",
                "planner unavailable; deterministic result kept",
                phase,
            )
        else:
            plan, answer = planned
            model = settings.openai_model
            _record(
                steps,
                "plan",
                f"{model} produced {len(plan)} step(s)",
                phase,
            )

    return AgentRunResponse(
        url=target_url,
        final_url=scraped["final_url"],
        title=scraped["title"],
        description=scraped["description"],
        status_code=scraped["status_code"],
        instruction=request.instruction,
        text=full_text[:MAX_TEXT_CHARS],
        text_truncated=text_truncated,
        headings=scraped["headings"],
        links=links,
        screenshot_base64=scraped["screenshot_base64"],
        steps=steps,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        plan=plan,
        answer=answer,
        model=model,
    )


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    _: object = Depends(rate_limited_user),
) -> AgentRunResponse:
    """Visit a URL, extract its content, and report what the agent did."""
    return await execute_run(request)


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """Report which optional capabilities this deployment has."""
    return {
        "browser": {
            "engine": "chromium",
            "headless": True,
            "reused_across_requests": True,
        },
        "ai": {
            "configured": ai_available(),
            "provider": "openai",
            "model": settings.openai_model if ai_available() else None,
        },
        "auth": {
            "required": settings.auth_required,
            "provider": "supabase" if settings.auth_required else None,
        },
        "tasks": {
            "enabled": True,
            "statuses": ["queued", "running", "succeeded", "failed", "cancelled"],
            "cancellable": True,
        },
        "limits": {
            "max_text_chars": MAX_TEXT_CHARS,
            "max_links": 200,
            "max_timeout_ms": 120_000,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
        },
    }
