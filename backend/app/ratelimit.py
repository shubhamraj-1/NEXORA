"""In-process sliding-window rate limiting for expensive agent endpoints."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, status

from .auth import AuthUser, current_user
from .config import settings


@dataclass
class RateLimiter:
    """Allow at most ``limit`` events per ``window_seconds`` per key."""

    limit: int
    window_seconds: float = 60.0
    _events: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def check(self, key: str) -> tuple[bool, int]:
        """Consume one slot. Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        async with self._lock:
            bucket = self._events[key]
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()

            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return False, retry_after

            bucket.append(now)
            return True, 0

    def clear(self) -> None:
        """Drop all buckets (used by tests)."""
        self._events.clear()


rate_limiter = RateLimiter(
    limit=settings.rate_limit_per_minute,
    window_seconds=float(settings.rate_limit_window_seconds),
)


async def rate_limited_user(
    request: Request,
    user: AuthUser | None = Depends(current_user),
) -> AuthUser | None:
    """FastAPI dependency combining Supabase identity and rate limiting."""
    identity = user.subject if user else (request.client.host if request.client else "local")
    allowed, retry_after = await rate_limiter.check(identity)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
    return user
