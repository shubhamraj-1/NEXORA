"""Server-side Supabase persistence using the service role key only.

The browser never sees these credentials. All writes are keyed by the verified
Supabase user id from the access token; RLS still protects direct client reads.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

import httpx

from .config import settings

if TYPE_CHECKING:  # avoid circular import: tasks.py imports this module
    from .tasks import TaskRecord

logger = logging.getLogger(__name__)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def configured() -> bool:
    return bool(
        settings.supabase_url
        and settings.supabase_service_role_key
        and settings.database_configured
    )


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    key = settings.supabase_service_role_key or ""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _rest(path: str) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1/{path.lstrip('/')}"


async def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: object | None = None,
) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method,
                url,
                headers=headers or _headers(),
                json=json_body,
            )
        if response.status_code >= 400:
            logger.warning(
                "Supabase write failed %s %s: %s",
                method,
                response.status_code,
                response.text[:300],
            )
            return False
        return True
    except Exception as exc:  # pragma: no cover - network defensive
        logger.warning("Supabase write error: %s", exc)
        return False


async def upsert_task(task: TaskRecord) -> bool:
    """Persist a task snapshot to ``public.tasks``."""
    if not configured() or not _is_uuid(task.owner):
        return False
    payload = {
        "id": task.id,
        "user_id": task.owner,
        "status": task.status.value,
        "progress": task.progress,
        "url": str(task.request.url),
        "instruction": task.request.instruction,
        "error": task.error,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
    return await _request(
        "POST",
        _rest("tasks"),
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json_body=payload,
    )


async def replace_task_logs(task: TaskRecord) -> bool:
    """Replace a task's log rows so repeated syncs stay idempotent."""
    if not configured() or not _is_uuid(task.owner):
        return False
    await _request(
        "DELETE",
        _rest(f"task_logs?task_id=eq.{task.id}&user_id=eq.{task.owner}"),
    )
    if not task.logs:
        return True
    payload = [
        {
            "task_id": task.id,
            "user_id": task.owner,
            "timestamp": entry.timestamp,
            "level": entry.level,
            "message": entry.message,
        }
        for entry in task.logs
    ]
    return await _request("POST", _rest("task_logs"), json_body=payload)


async def upsert_task_result(task: TaskRecord) -> bool:
    """Persist a result without the large base64 screenshot payload."""
    if not configured() or not _is_uuid(task.owner) or task.result is None:
        return False
    stored: dict[str, object] = task.result.model_dump()
    stored.pop("screenshot_base64", None)
    payload = {
        "task_id": task.id,
        "user_id": task.owner,
        "result": stored,
        "saved_at": task.updated_at,
    }
    return await _request(
        "POST",
        _rest("task_results"),
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json_body=payload,
    )
