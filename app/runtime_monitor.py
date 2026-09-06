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

        if not running and exitcode is None:
            return
        if not settings.bot_owner_user_id or not settings.supabase_db_url:
            return

        last_error = None
        state = "RUNNING" if running else "STOPPED"
        if exitcode not in (None, 0) and exitcode != self._last_exitcode:
            state = "CRASHED"
            last_error = f"Freqtrade child exited with code {exitcode}"
            logger.error(last_error)
        self._last_exitcode = exitcode

        now = datetime.now(UTC)
        db_healthy = False
        market_data_healthy = False
        websocket_healthy = False
        private_stream_healthy = False

        try:
            async with await psycopg.AsyncConnection.connect(settings.supabase_db_url, connect_timeout=8) as conn:
                db_healthy = True
                async with conn.cursor() as cur:
                    # A fresh snapshot is the only evidence we accept for market-data health.
                    await cur.execute(
                        "select captured_at from public.market_snapshots order by captured_at desc limit 1"
                    )
                    row = await cur.fetchone()
                    if row and row[0]:
                        age = (now - row[0]).total_seconds()
                        market_data_healthy = age <= max(30.0, settings.process_throttle_secs * 6)
                        websocket_healthy = market_data_healthy
                    if settings.is_live:
                        # Private-stream health cannot be inferred from process liveness.
                        # It remains false until the exchange reconciliation layer confirms it.
                        private_stream_healthy = False
                    else:
                        private_stream_healthy = True

                    if running and not market_data_healthy:
                        state = "RUNNING_UNVERIFIED"
                        last_error = "Engine is alive but no fresh market snapshot has been confirmed"

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
                            websocket_healthy,
                            market_data_healthy,
                            private_stream_healthy,
                            db_healthy,
                            now,
                            last_error,
                        ),
                    )
                await conn.commit()
        except Exception as exc:
            logger.exception("Health database check failed")
            # Do not claim the database is healthy when the write/check itself failed.
            logger.error("Health check error: %s", exc)


monitor = RuntimeMonitor()
