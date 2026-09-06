from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime

import psycopg

from .config import settings
from .freqtrade_runtime import runtime

logger = logging.getLogger(__name__)


class RuntimeMonitor:
    def __init__(self, interval_seconds: float = 15.0) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._last_exitcode: int | None = None
        self._restart_times: deque[datetime] = deque()

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
        if not running and exitcode is None:
            return
        if not settings.bot_owner_user_id or not settings.supabase_db_url:
            return

        last_error = None
        state = "RUNNING" if running else "STOPPED"
        crashed = exitcode not in (None, 0)
        if crashed and exitcode != self._last_exitcode:
            state = "CRASHED"
            last_error = f"Freqtrade child exited with code {exitcode}"
            logger.error(last_error)
        self._last_exitcode = exitcode

        now = datetime.now(UTC)
        market_data_healthy = False
        websocket_healthy = False
        private_stream_healthy = not settings.is_live

        try:
            async with await psycopg.AsyncConnection.connect(settings.supabase_db_url, connect_timeout=8) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("select captured_at from public.market_snapshots order by captured_at desc limit 1")
                    row = await cur.fetchone()
                    if row and row[0]:
                        age = (now - row[0]).total_seconds()
                        market_data_healthy = age <= max(30.0, settings.process_throttle_secs * 6)
                        websocket_healthy = market_data_healthy
                    if running and not market_data_healthy:
                        state = "RUNNING_UNVERIFIED"
                        last_error = "Engine is alive but no fresh market snapshot has been confirmed"

                    await cur.execute(
                        """
                        insert into public.bot_health
                        (user_id, mode, state, websocket_healthy, market_data_healthy,
                         private_stream_healthy, db_healthy, last_cycle_at, last_error)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        on conflict (user_id, mode) do update set
                          state=excluded.state,
                          websocket_healthy=excluded.websocket_healthy,
                          market_data_healthy=excluded.market_data_healthy,
                          private_stream_healthy=excluded.private_stream_healthy,
                          db_healthy=excluded.db_healthy,
                          last_cycle_at=excluded.last_cycle_at,
                          last_error=excluded.last_error,
                          updated_at=now()
                        """,
                        (settings.bot_owner_user_id, settings.trading_mode, state,
                         websocket_healthy, market_data_healthy, private_stream_healthy,
                         True, now, last_error),
                    )
                await conn.commit()
        except Exception as exc:
            logger.exception("Health database check failed: %s", exc)
            return

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
