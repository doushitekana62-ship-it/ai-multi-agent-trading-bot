from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections import deque
from datetime import UTC, datetime

from .config import settings
from .freqtrade_runtime import _writable_sqlite_path, runtime
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

    @staticmethod
    def _db_healthy() -> bool:
        try:
            path = _writable_sqlite_path()
            with sqlite3.connect(path, timeout=2) as conn:
                result = conn.execute("PRAGMA quick_check").fetchone()
            return bool(result and result[0] == "ok")
        except Exception:
            return False

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
        ws_healthy = bool(collector.ws_healthy and collector.ws_last_message_at)
        state = "RUNNING" if running else "STOPPED"
        last_error = status.get("error")
        crashed = exitcode not in (None, 0)
        if crashed and exitcode != self._last_exitcode:
            state = "CRASHED"
            last_error = status.get("error") or f"Freqtrade worker exited with code {exitcode}"
            logger.error(last_error)
        elif running and not market_data_healthy:
            state = "RUNNING_UNVERIFIED"
            last_error = last_error or "Engine is alive but no fresh market snapshot has been confirmed"
        elif running and not ws_healthy:
            state = "RUNNING_DEGRADED"
            last_error = last_error or "Indodax market websocket is not healthy; REST fallback remains active"
        db_healthy = await asyncio.to_thread(self._db_healthy)
        self._last_exitcode = exitcode
        self.health = {
            "state": state,
            "market_data_healthy": market_data_healthy,
            "market_data_source": "websocket_with_rest_fallback",
            "websocket_healthy": ws_healthy,
            "websocket_last_message_at": collector.ws_last_message_at,
            "websocket_reconnects": collector.ws_reconnects,
            "private_stream_healthy": None if settings.is_live else True,
            "db_healthy": db_healthy,
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
                    await asyncio.to_thread(runtime.start)
                    logger.info("Paper runtime restarted after crash")
                except Exception:
                    logger.exception("Paper runtime restart failed")
        elif crashed and settings.runtime_restart_enabled and settings.is_live:
            logger.critical("Live runtime crashed; automatic restart is disabled until reconciliation is available")


monitor = RuntimeMonitor()
