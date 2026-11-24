"""OpenAI-backed planning layer for NEXORA agent runs.

The planner is optional: without ``OPENAI_API_KEY`` the API keeps returning the
deterministic extraction it already produces. When a key is present the model
turns the user's instruction plus the extracted page into a short plan and a
grounded answer.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from .config import settings
from .schemas import ExtractedLink

logger = logging.getLogger(__name__)

_async_client: AsyncOpenAI | None = None


def ai_available() -> bool:
    """Whether an API key is configured."""
    return settings.ai_enabled


def _get_client() -> AsyncOpenAI:
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_s,
            max_retries=1,
        )
    return _async_client


SYSTEM_PROMPT = """You are the planning layer of NEXORA, a web intelligence agent.
You receive one page and a user instruction. Work only from the supplied page.

Reply with a single JSON object and nothing else:
{"plan": ["short imperative step", "..."], "answer": "answer text"}

Rules:
- "plan" has 2 to 6 steps describing how the answer was derived from this page.
- "answer" directly answers the instruction, using only facts present in the page.
- If the page does not contain the answer, say so plainly in "answer".
- Keep the answer under 120 words. No markdown, no code fences, no citations list.
"""


class PlanPayload(BaseModel):
    """Structured model output."""

    plan: list[str] = Field(default_factory=list)
    answer: str = Field(min_length=1)


def _messages(
    instruction: str,
    url: str,
    title: str,
    text: str,
    links: list[ExtractedLink],
) -> list[dict[str, str]]:
    link_lines = (
        "\n".join(f"- {link.text[:80]} -> {link.href}" for link in links[:25])
        or "(no links)"
    )
    user = (
        f"Instruction: {instruction}\n\n"
        f"Page URL: {url}\n"
        f"Page title: {title}\n\n"
        f"Page content:\n{text[: settings.max_ai_context_chars]}\n\n"
        f"Links:\n{link_lines}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _parse(content: str) -> PlanPayload:
    """Parse model output, tolerating a stray code fence."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return PlanPayload.model_validate_json(cleaned)


async def plan_run(
    *,
    instruction: str,
    url: str,
    title: str,
    text: str,
    links: list[ExtractedLink],
) -> tuple[list[str], str] | None:
    """Ask the model for a plan and answer.

    Returns ``None`` when AI is disabled, misconfigured or failing; callers keep
    the deterministic result rather than turning a model hiccup into a 5xx.
    """
    if not settings.ai_enabled:
        return None

    try:
        completion: Any = await _get_client().chat.completions.create(
            model=settings.openai_model,
            messages=_messages(instruction, url, title, text, links),
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = completion.choices[0].message.content or "{}"
        payload = _parse(content)
    except ValidationError:
        logger.warning("Planner returned unusable JSON; using deterministic result")
        return None
    except json.JSONDecodeError:
        logger.warning("Planner returned invalid JSON; using deterministic result")
        return None
    except Exception:
        logger.warning("Planner call failed; using deterministic result", exc_info=True)
        return None

    plan = [step.strip() for step in payload.plan if step.strip()]
    answer = payload.answer.strip()
    if not answer:
        logger.warning("Planner returned an empty answer; using deterministic result")
        return None
    return plan[: settings.ai_max_plan_steps], answer
