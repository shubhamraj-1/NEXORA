"""Cancellable background task workflow for NEXORA runs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .agent import execute_run
from .auth import AuthUser
from .ratelimit import rate_limited_user
from .schemas import AgentRunRequest, AgentRunResponse
from . import supabase_store

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Lifecycle states exposed to the dashboard."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_STATUSES = {TaskStatus.succeeded, TaskStatus.failed, TaskStatus.cancelled}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskLog(BaseModel):
    """A single structured event in a task's execution log."""

    timestamp: str
    level: str
    message: str


class TaskRecord(BaseModel):
    """Full persisted representation of a task (in-memory for this deployment)."""

    id: str
    owner: str
    status: TaskStatus
    progress: int
    created_at: str
    updated_at: str
    request: AgentRunRequest
    result: AgentRunResponse | None = None
    error: str | None = None
    logs: list[TaskLog] = []


class TaskManager:
    """Owns in-memory task records and their asyncio handles."""

    def __init__(self, max_history: int = 200) -> None:
        self._records: dict[str, TaskRecord] = {}
        self._handles: dict[str, asyncio.Task[None]] = {}
        self._order: deque[str] = deque()
        self._max_history = max_history
        self._lock = asyncio.Lock()

    async def create(self, request: AgentRunRequest, owner: str) -> TaskRecord:
        task_id = uuid.uuid4().hex
        timestamp = _now()
        record = TaskRecord(
            id=task_id,
            owner=owner,
            status=TaskStatus.queued,
            progress=5,
            created_at=timestamp,
            updated_at=timestamp,
            request=request,
            logs=[TaskLog(timestamp=timestamp, level="info", message="Task queued.")],
        )
        async with self._lock:
            self._records[task_id] = record
            self._order.append(task_id)
            self._trim_locked()

        handle = asyncio.create_task(self._execute(task_id), name=f"nexora-task-{task_id}")
        async with self._lock:
            self._handles[task_id] = handle
        return record

    async def list(self, owner: str) -> list[TaskRecord]:
        async with self._lock:
            ids = list(reversed(self._order))
            records = [self._records[item] for item in ids if item in self._records]
        return [record for record in records if record.owner == owner]

    async def get(self, task_id: str, owner: str) -> TaskRecord:
        async with self._lock:
            record = self._records.get(task_id)
        if record is None or record.owner != owner:
            raise HTTPException(status_code=404, detail="Task not found.")
        return record

    async def logs(self, task_id: str, owner: str) -> list[TaskLog]:
        return (await self.get(task_id, owner)).logs

    async def result(self, task_id: str, owner: str) -> AgentRunResponse:
        record = await self.get(task_id, owner)
        if record.status != TaskStatus.succeeded or record.result is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Task is {record.status.value}; no result available yet.",
            )
        return record.result

    async def cancel(self, task_id: str, owner: str) -> TaskRecord:
        record = await self.get(task_id, owner)
        if record.status in TERMINAL_STATUSES:
            return record

        async with self._lock:
            handle = self._handles.get(task_id)
        if handle is not None:
            handle.cancel()

        async with self._lock:
            current = self._records[task_id]
            current.status = TaskStatus.cancelled
            current.progress = 100
            current.updated_at = _now()
            current.logs.append(
                TaskLog(timestamp=current.updated_at, level="warn", message="Task cancelled by user.")
            )
        await self._persist(task_id)
        async with self._lock:
            return current

    async def shutdown(self) -> None:
        """Cancel all in-flight tasks on application shutdown."""
        async with self._lock:
            handles = list(self._handles.values())
        for handle in handles:
            handle.cancel()
        if handles:
            await asyncio.gather(*handles, return_exceptions=True)

    def _trim_locked(self) -> None:
        while len(self._order) > self._max_history:
            task_id = self._order.popleft()
            self._records.pop(task_id, None)
            self._handles.pop(task_id, None)

    async def _mutate(self, task_id: str, mutation: Any) -> None:
        async with self._lock:
            record = self._records.get(task_id)
            if record is not None:
                mutation(record)

    async def _persist(self, task_id: str, include_result: bool = False) -> None:
        """Mirror in-memory state into Supabase when service credentials exist."""
        try:
            record = await self.get_by_id(task_id)
            await supabase_store.upsert_task(record)
            await supabase_store.replace_task_logs(record)
            if include_result and record.result is not None:
                await supabase_store.upsert_task_result(record)
        except Exception:  # pragma: no cover - persistence must not break a run
            logger.warning("Could not persist task %s to Supabase", task_id, exc_info=True)

    async def _execute(self, task_id: str) -> None:
        await self._mutate(
            task_id,
            lambda record: (
                setattr(record, "status", TaskStatus.running),
                setattr(record, "progress", 20),
                setattr(record, "updated_at", _now()),
                record.logs.append(
                    TaskLog(timestamp=_now(), level="info", message="Browser run started.")
                ),
            ),
        )
        await self._persist(task_id)

        try:
            request = (await self.get_by_id(task_id)).request
            result = await execute_run(request)
            await self._mutate(
                task_id,
                lambda record: (
                    setattr(record, "status", TaskStatus.succeeded),
                    setattr(record, "progress", 100),
                    setattr(record, "updated_at", _now()),
                    setattr(record, "result", result),
                    record.logs.extend(
                        TaskLog(timestamp=_now(), level="info", message=f"{step.action}: {step.detail}")
                        for step in result.steps
                    ),
                    record.logs.append(
                        TaskLog(timestamp=_now(), level="info", message="Task completed.")
                    ),
                ),
            )
            await self._persist(task_id, include_result=True)
        except asyncio.CancelledError:
            await self._mutate(
                task_id,
                lambda record: (
                    setattr(record, "status", TaskStatus.cancelled),
                    setattr(record, "progress", 100),
                    setattr(record, "updated_at", _now()),
                    record.logs.append(
                        TaskLog(timestamp=_now(), level="warn", message="Task cancelled.")
                    ),
                ),
            )
            await self._persist(task_id)
            raise
        except HTTPException as exc:
            await self._fail(task_id, str(exc.detail))
        except Exception as exc:  # pragma: no cover - defensive
            await self._fail(task_id, str(exc))

    async def get_by_id(self, task_id: str) -> TaskRecord:
        async with self._lock:
            record = self._records.get(task_id)
        if record is None:
            raise RuntimeError(f"Task {task_id} disappeared.")
        return record

    async def _fail(self, task_id: str, message: str) -> None:
        await self._mutate(
            task_id,
            lambda record: (
                setattr(record, "status", TaskStatus.failed),
                setattr(record, "progress", 100),
                setattr(record, "updated_at", _now()),
                setattr(record, "error", message),
                record.logs.append(TaskLog(timestamp=_now(), level="error", message=message)),
            ),
        )
        await self._persist(task_id)


task_manager = TaskManager()


def _owner(user: AuthUser | None) -> str:
    return user.subject if user else "anonymous"


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=TaskRecord)
async def create_task(
    request: AgentRunRequest,
    user: AuthUser | None = Depends(rate_limited_user),
) -> TaskRecord:
    """Queue a new browser run and return its id for polling."""
    return await task_manager.create(request, _owner(user))


@router.get("", response_model=list[TaskRecord])
async def list_tasks(
    user: AuthUser | None = Depends(rate_limited_user),
) -> list[TaskRecord]:
    """List the caller's tasks, newest first."""
    return await task_manager.list(_owner(user))


@router.get("/{task_id}", response_model=TaskRecord)
async def get_task(
    task_id: str,
    user: AuthUser | None = Depends(rate_limited_user),
) -> TaskRecord:
    return await task_manager.get(task_id, _owner(user))


@router.get("/{task_id}/logs", response_model=list[TaskLog])
async def get_task_logs(
    task_id: str,
    user: AuthUser | None = Depends(rate_limited_user),
) -> list[TaskLog]:
    return await task_manager.logs(task_id, _owner(user))


@router.get("/{task_id}/result", response_model=AgentRunResponse)
async def get_task_result(
    task_id: str,
    user: AuthUser | None = Depends(rate_limited_user),
) -> AgentRunResponse:
    return await task_manager.result(task_id, _owner(user))


@router.delete("/{task_id}", response_model=TaskRecord)
async def cancel_task(
    task_id: str,
    user: AuthUser | None = Depends(rate_limited_user),
) -> TaskRecord:
    return await task_manager.cancel(task_id, _owner(user))
