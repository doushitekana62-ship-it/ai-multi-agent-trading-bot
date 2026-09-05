from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from .config import settings
from .freqtrade_runtime import runtime
from .supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class RuntimeMonitor:
    def __init__(self, interval_seconds: float = 15.0) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_exitcode: int | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="runtime-monitor")
        logger.info("Runtime monitor started interval=%ss", self.interval_seconds)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Runtime monitor stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._publish_health()
            except Exception:
                logger.exception("Runtime monitor iteration failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def _publish_health(self) -> None:
        status = runtime.status()
        running = bool(status["running"])
        exitcode = status.get("exitcode")
        last_error = None
        state = "RUNNING" if running else "STOPPED"

        if exitcode not in (None, 0) and exitcode != self._last_exitcode:
            state = "CRASHED"
            last_error = f"Freqtrade child exited with code {exitcode}"
            logger.error(last_error)
        self._last_exitcode = exitcode

        if not settings.bot_owner_user_id or not settings.supabase_service_role_key:
            return

        now = datetime.now(UTC).isoformat()
        payload = {
            "user_id": settings.bot_owner_user_id,
            "mode": settings.trading_mode,
            "state": state,
            "websocket_healthy": running,
            "market_data_healthy": running,
            "private_stream_healthy": running if settings.is_live else False,
            "db_healthy": True,
            "last_cycle_at": now,
            "last_error": last_error,
        }
        await SupabaseClient().upsert(
            "bot_health",
            payload,
            on_conflict="user_id,mode",
        )


monitor = RuntimeMonitor()
