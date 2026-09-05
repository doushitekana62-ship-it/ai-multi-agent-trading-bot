from __future__ import annotations

import asyncio
import logging
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

        # Do not open a database connection every 15 seconds while the engine
        # is intentionally stopped. This also keeps platform startup cheap.
        if not running and exitcode is None:
            return

        last_error = None
        state = "RUNNING" if running else "STOPPED"
        if exitcode not in (None, 0) and exitcode != self._last_exitcode:
            state = "CRASHED"
            last_error = f"Freqtrade child exited with code {exitcode}"
            logger.error(last_error)
        self._last_exitcode = exitcode

        if not settings.bot_owner_user_id or not settings.supabase_db_url:
            return

        now = datetime.now(UTC)
        async with await psycopg.AsyncConnection.connect(settings.supabase_db_url, connect_timeout=8) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    insert into public.bot_health (
                        user_id, mode, state, websocket_healthy,
                        market_data_healthy, private_stream_healthy,
                        db_healthy, last_cycle_at, last_error
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (user_id, mode) do update set
                        state = excluded.state,
                        websocket_healthy = excluded.websocket_healthy,
                        market_data_healthy = excluded.market_data_healthy,
                        private_stream_healthy = excluded.private_stream_healthy,
                        db_healthy = excluded.db_healthy,
                        last_cycle_at = excluded.last_cycle_at,
                        last_error = excluded.last_error,
                        updated_at = now()
                    """,
                    (
                        settings.bot_owner_user_id,
                        settings.trading_mode,
                        state,
                        running,
                        running,
                        running if settings.is_live else False,
                        True,
                        now,
                        last_error,
                    ),
                )
            await conn.commit()


monitor = RuntimeMonitor()
