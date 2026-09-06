from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime

from .config import settings
from .freqtrade_runtime import runtime
from .market_snapshot import collector

logger = logging.getLogger(__name__)


class RuntimeMonitor:
    def __init__(self, interval_seconds: float = 15.0) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_exitcode: int | None = None
        self._restart_times: deque[datetime] = deque()
        self.health: dict = {"state": "STARTING", "market_data_healthy": False, "updated_at": None}

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

    def _restart_allowed(self, now: datetime) -> bool:
        if not settings.runtime_restart_enabled or settings.is_live:
            return False
        while self._restart_times and (now - self._restart_times[0]).total_seconds() > 300:
            self._restart_times.popleft()
        return len(self._restart_times) < 3

    async def _publish_health(self) -> None:
        status = runtime.status()
        running = bool(status["running"])
        exitcode = status.get("exitcode")
        now = datetime.now(UTC)
        latest = list(collector.latest.values())
        market_data_healthy = any(
            (now - datetime.fromisoformat(row["captured_at"])).total_seconds() <= max(30.0, settings.process_throttle_secs * 6)
            for row in latest
            if row.get("captured_at")
        )
        state = "RUNNING" if running else "STOPPED"
        last_error = None
        crashed = exitcode not in (None, 0)
        if crashed and exitcode != self._last_exitcode:
            state = "CRASHED"
            last_error = f"Freqtrade child exited with code {exitcode}"
            logger.error(last_error)
        elif running and not market_data_healthy:
            state = "RUNNING_UNVERIFIED"
            last_error = "Engine is alive but no fresh market snapshot has been confirmed"
        self._last_exitcode = exitcode
        self.health = {
            "state": state,
            "market_data_healthy": market_data_healthy,
            "websocket_healthy": market_data_healthy,
            "private_stream_healthy": not settings.is_live,
            "db_healthy": True,
            "last_cycle_at": now.isoformat(),
            "last_error": last_error,
            "updated_at": now.isoformat(),
        }

        if crashed and self._restart_allowed(now):
            self._restart_times.append(now)
            logger.warning("Scheduling safe paper-mode runtime restart attempt=%s", len(self._restart_times))
            await asyncio.sleep(settings.runtime_restart_delay)
            if not self._stop.is_set() and not runtime.running:
                try:
                    runtime.start()
                    logger.info("Paper runtime restarted after crash")
                except Exception:
                    logger.exception("Paper runtime restart failed")
        elif crashed and settings.runtime_restart_enabled and settings.is_live:
            logger.critical("Live runtime crashed; automatic restart is disabled until reconciliation is available")


monitor = RuntimeMonitor()
