from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import psycopg

from .config import settings
from .freqtrade_runtime import runtime

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Mirror Freqtrade private persistence into public application state."""

    def __init__(self, interval_seconds: float = 15.0) -> None:
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="reconciliation")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            if runtime.running and settings.supabase_db_url:
                try:
                    await self.reconcile_once()
                except Exception:
                    logger.exception("Reconciliation failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def _rows(self, cur, table: str) -> list[dict]:
        await cur.execute(f"select * from freqtrade.{table}")
        columns = [item.name for item in cur.description]
        return [dict(zip(columns, row)) for row in await cur.fetchall()]

    async def reconcile_once(self) -> None:
        if not settings.bot_owner_user_id:
            return
        async with await psycopg.AsyncConnection.connect(settings.supabase_db_url, connect_timeout=8) as conn:
            async with conn.cursor() as cur:
                trades = await self._rows(cur, "trades")
                orders = await self._rows(cur, "orders")

                for trade in trades:
                    external_id = str(trade.get("id")) if trade.get("id") is not None else None
                    if not external_id:
                        continue
                    status = "open" if trade.get("is_open") else "closed"
                    opened_at = trade.get("open_date") or datetime.now(UTC)
                    closed_at = trade.get("close_date")
                    await cur.execute(
                        "select id from public.positions where user_id=%s and external_trade_id=%s limit 1",
                        (settings.bot_owner_user_id, external_id),
                    )
                    existing = await cur.fetchone()
                    values = (
                        trade.get("pair") or "UNKNOWN",
                        "short" if trade.get("is_short") else "long",
                        trade.get("open_rate"), trade.get("close_rate"), trade.get("stop_loss"),
                        trade.get("amount"), trade.get("close_profit_abs"), status, opened_at, closed_at,
                    )
                    if existing:
                        await cur.execute(
                            """update public.positions set symbol=%s, side=%s, entry_price=%s,
                            exit_price=%s, sl_price=%s, amount=%s, pnl=%s, status=%s,
                            opened_at=%s, closed_at=%s where id=%s""",
                            (*values, existing[0]),
                        )
                    else:
                        await cur.execute(
                            """insert into public.positions
                            (user_id, external_trade_id, symbol, side, entry_price, exit_price,
                             sl_price, amount, pnl, status, opened_at, closed_at)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (settings.bot_owner_user_id, external_id, *values),
                        )

                for order in orders:
                    exchange_id = order.get("order_id")
                    if not exchange_id:
                        continue
                    side = order.get("side") or order.get("ft_order_side") or "buy"
                    if side == "stoploss":
                        side = "sell"
                    if side not in ("buy", "sell"):
                        side = "buy"
                    status = order.get("status") or ("open" if order.get("ft_is_open") else "closed")
                    if status == "canceled":
                        status = "cancelled"
                    if status not in ("pending", "open", "closed", "cancelled", "rejected", "unknown"):
                        status = "unknown"
                    order_date = order.get("order_date") or datetime.now(UTC)
                    update_date = order.get("order_update_date") or order_date
                    await cur.execute(
                        "select id from public.orders where user_id=%s and exchange_order_id=%s limit 1",
                        (settings.bot_owner_user_id, str(exchange_id)),
                    )
                    existing = await cur.fetchone()
                    values = (
                        order.get("ft_pair") or order.get("symbol") or "UNKNOWN",
                        side, order.get("order_type") or "market", status,
                        order.get("price"), order.get("amount") or order.get("ft_amount"),
                        order.get("filled"), order.get("average"), order.get("ft_fee_base"),
                        order_date, update_date,
                    )
                    if existing:
                        await cur.execute(
                            """update public.orders set symbol=%s, side=%s, order_type=%s,
                            status=%s, price=%s, amount=%s, filled=%s, average_price=%s,
                            fee=%s, created_at=%s, updated_at=%s where id=%s""",
                            (*values, existing[0]),
                        )
                    else:
                        await cur.execute(
                            """insert into public.orders
                            (user_id, exchange_order_id, symbol, side, order_type, status,
                             price, amount, filled, average_price, fee, created_at, updated_at)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (settings.bot_owner_user_id, str(exchange_id), *values),
                        )
            await conn.commit()


reconciler = ReconciliationService()
