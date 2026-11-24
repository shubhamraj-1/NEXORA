"""Shared Playwright browser lifecycle for the NEXORA API.

Playwright's driver is a Node process, so asyncio must be able to spawn child
processes. On Windows only ``ProactorEventLoop`` can do that, while uvicorn
installs a ``SelectorEventLoop`` whenever ``--reload`` or ``--workers`` is used.
Uvicorn hands that loop straight to ``asyncio.Runner``, so it cannot be replaced
from application code. Playwright therefore gets a private Proactor loop on a
worker thread, and every browser call is dispatched onto it.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from playwright.async_api import Browser, Page, Playwright, async_playwright

logger = logging.getLogger(__name__)

T = TypeVar("T")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36 NEXORA/0.1"
)

DEFAULT_TIMEOUT_MS = 30_000


def _new_worker_loop() -> asyncio.AbstractEventLoop:
    """Create the loop Playwright runs on.

    ``ProactorEventLoop`` is instantiated directly because it is the only loop
    on Windows that supports subprocess transports, and the process-wide policy
    may already have been changed by another component.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def _worker_exception_handler(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any]
) -> None:
    """Drop Playwright's benign driver-teardown race from the shutdown logs.

    A Ctrl+C on Windows reaches every process in the console group, including
    the Node driver. The driver then exits before Playwright can shut down
    gracefully, so the transport stores "Connection closed while reading from
    the driver" on a future that no longer has an awaiter, and asyncio reports
    it as never retrieved when the future is collected. Shutdown has already
    completed at that point, so the report is noise. Anything else is passed
    through untouched.
    """
    exception = context.get("exception")
    if (
        context.get("message") == "Future exception was never retrieved"
        and exception is not None
        and "Connection closed while reading from the driver" in str(exception)
    ):
        return
    loop.default_exception_handler(context)


class BrowserUnavailableError(RuntimeError):
    """Raised when a browser call arrives without a running worker loop."""


class BrowserManager:
    """Owns the Playwright driver and a shared Chromium browser."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    # -- worker thread ---------------------------------------------------

    def _run_loop(self, ready: threading.Event) -> None:
        loop = _new_worker_loop()
        loop.set_exception_handler(_worker_exception_handler)
        asyncio.set_event_loop(loop)
        self._loop = loop
        ready.set()
        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    async def _dispatch(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run a coroutine on the Playwright loop and await it here."""
        loop = self._loop
        if loop is None or not loop.is_running():
            raise BrowserUnavailableError("The Playwright worker loop is not running.")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wrap_future(future)

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Launch the worker loop, Playwright and Chromium."""
        async with self._lock:
            if self._thread is not None:
                return
            ready = threading.Event()
            thread = threading.Thread(
                target=self._run_loop,
                args=(ready,),
                name="nexora-playwright",
                daemon=True,
            )
            thread.start()
            self._thread = thread

            started = await asyncio.to_thread(ready.wait, 10.0)
            if not started or self._loop is None:
                raise RuntimeError("Timed out starting the Playwright worker loop.")

            try:
                await self._dispatch(self._launch())
            except BaseException:
                await self._shutdown_worker()
                raise

    async def _launch(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def _teardown(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def stop(self) -> None:
        """Close the browser, stop Playwright and join the worker thread."""
        async with self._lock:
            await self._shutdown_worker()

    async def _shutdown_worker(self) -> None:
        loop, thread = self._loop, self._thread
        if loop is None or thread is None:
            return
        try:
            await self._dispatch(self._teardown())
        except Exception:
            logger.exception("Playwright did not shut down cleanly")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            await asyncio.to_thread(thread.join, 10.0)
            self._loop = None
            self._thread = None
            self._browser = None
            self._playwright = None

    # -- request handling ------------------------------------------------

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("Chromium is not running; the lifespan did not start it.")
        return self._browser

    @asynccontextmanager
    async def page(self) -> AsyncIterator[Page]:
        """Yield a fresh page in its own context, closing both on exit.

        Only valid inside the Playwright loop; use :meth:`run_with_page` from
        request handlers.
        """
        context = await self.browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        try:
            page = await context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            yield page
        finally:
            await context.close()

    async def run_with_page(
        self, action: Callable[[Page], Awaitable[T]]
    ) -> T:
        """Run ``action`` with a fresh page, on the Playwright worker loop."""
        return await self._dispatch(self._with_page(action))

    async def _with_page(self, action: Callable[[Page], Awaitable[T]]) -> T:
        async with self.page() as page:
            return await action(page)


browser_manager = BrowserManager()
