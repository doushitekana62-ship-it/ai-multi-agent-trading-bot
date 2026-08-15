"""
Paper Trading Engine v2

Tugas:
1. Menjalankan simulasi BUY / SELL
2. Mengelola LONG / SHORT position
3. Menghitung realized & unrealized PnL
4. Mengelola Stop Loss / Take Profit
5. Mengelola balance dan equity
6. Menyimpan trade history
7. Tidak mengambil keputusan trading sendiri

Decision flow:

Orchestrator
    ↓
Risk Engine
    ↓
Decision Engine
    ↓
Execution Gate
    ↓
PaperTradingEngine
"""

import logging
import uuid
from datetime import datetime,timezone
from typing import Dict, List, Optional, Any


logger = logging.getLogger(__name__)

class PaperTradingEngine:

    def __init__(
        self,
        initial_balance: float = 10000.0,
        max_position_size: float = 0.20,
    ):
        self.initial_balance = float(initial_balance)

        self.balance = float(initial_balance)

        self.max_position_size = float(max_position_size)

        self.positions: Dict[str, Dict[str, Any]] = {}

        self.trade_history: List[Dict[str, Any]] = []

        self.order_history: List[Dict[str, Any]] = []
    """
    Initialize Paper Trading Engine.

    Supports:

    Direct arguments:

        PaperTradingEngine(
            initial_balance=10000,
            max_position_size=0.20
        )

    Configuration dictionary:

        PaperTradingEngine({
            "initial_balance": 10000,
            "max_position_size": 0.20
        })
    """

    # ------------------------------------------------------
    # SUPPORT CONFIG DICTIONARY
    # ------------------------------------------------------

    if isinstance(initial_balance, dict):

        config = initial_balance

        initial_balance = config.get(
            "initial_balance",
            10000.0
        )

        max_position_size = config.get(
            "max_position_size",
            0.20
        )

    # ------------------------------------------------------
    # NORMALIZE VALUES
    # ------------------------------------------------------

    self.initial_balance = float(
        initial_balance
    )

    self.balance = float(
        initial_balance
    )

    self.max_position_size = float(
        max_position_size
    )

    # ------------------------------------------------------
    # POSITIONS
    # ------------------------------------------------------

    self.positions: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------
    # TRADE HISTORY
    # ------------------------------------------------------

    self.trade_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------
    # ORDER HISTORY
    # ------------------------------------------------------

    self.order_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------
    # STATISTICS
    # ------------------------------------------------------

    self.total_realized_pnl = 0.0

    self.total_trades = 0

    self.winning_trades = 0

    self.losing_trades = 0

    logger.info(
        "Paper Trading Engine initialized | "
        "Balance=$%.2f | "
        "Max Position=%.2f%%",
        self.balance,
        self.max_position_size * 100,
    )
    # ==========================================================
    # PORTFOLIO
    # ==========================================================

    def get_balance(self) -> float:
        """Return available cash balance."""
        return self.balance

    def get_equity(self, prices: Optional[Dict[str, float]] = None) -> float:
        """
        Return total portfolio equity.

        Equity =
        balance + unrealized PnL
        """

        prices = prices or {}

        unrealized_pnl = self.get_total_unrealized_pnl(prices)

        return self.balance + unrealized_pnl

    def get_total_unrealized_pnl(
        self,
        prices: Dict[str, float]
    ) -> float:
        """Calculate unrealized PnL across all positions."""

        total = 0.0

        for symbol, position in self.positions.items():

            current_price = prices.get(symbol)

            if current_price is None:
                continue

            total += self.calculate_unrealized_pnl(
                position,
                current_price
            )

        return total

    # ==========================================================
    # OPEN POSITION
    # ==========================================================

    def open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        position_size: float,
        confidence: float = 0.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Open LONG or SHORT position.

        side:
            BUY  -> LONG
            SELL -> SHORT

        position_size:
            0.08 = 8% portfolio
        """

        symbol = symbol.upper()
        side = side.upper()

        if side not in ("BUY", "SELL"):
            logger.warning(
                f"Invalid side: {side}"
            )
            return None

        if price <= 0:
            logger.warning(
                "Price must be greater than zero."
            )
            return None

        if position_size <= 0:
            logger.warning(
                "Position size must be greater than zero."
            )
            return None

        if position_size > self.max_position_size:
            logger.warning(
                f"Position size {position_size:.2%} "
                f"exceeds maximum {self.max_position_size:.2%}"
            )
            return None

        # Jangan membuka posisi kedua pada symbol yang sama
        if symbol in self.positions:

            logger.warning(
                f"{symbol} already has an active position."
            )

            return None

        # ------------------------------------------------------
        # Calculate capital
        # ------------------------------------------------------

        equity = self.get_equity()

        capital = equity * position_size

        if capital > self.balance:

            logger.warning(
                f"Insufficient balance | "
                f"Required=${capital:.2f} | "
                f"Balance=${self.balance:.2f}"
            )

            return None

        quantity = capital / price

        position_id = str(uuid.uuid4())

        position = {
            "position_id": position_id,
            "symbol": symbol,
            "side": side,
            "position_type": (
                "LONG"
                if side == "BUY"
                else "SHORT"
            ),
            "entry_price": float(price),
            "quantity": float(quantity),
            "capital": float(capital),
            "position_size": float(position_size),
            "confidence": float(confidence),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": 0.0,
        }

        # Reserve capital
        self.balance -= capital

        self.positions[symbol] = position

        order = {
            "order_id": str(uuid.uuid4()),
            "position_id": position_id,
            "symbol": symbol,
            "side": side,
            "action": "OPEN",
            "price": float(price),
            "quantity": float(quantity),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "FILLED",
        }

        self.order_history.append(order)

        logger.info(
            f"OPEN {position['position_type']} | "
            f"{symbol} | "
            f"Qty={quantity:.8f} | "
            f"Price=${price:.2f}"
        )

        return position.copy()

    # ==========================================================
    # CLOSE POSITION
    # ==========================================================

    def close_position(
        self,
        symbol: str,
        price: float,
        reason: str = "MANUAL",
    ) -> Optional[Dict[str, Any]]:
        """
        Close active position.
        """

        symbol = symbol.upper()

        if symbol not in self.positions:

            logger.warning(
                f"No active position for {symbol}"
            )

            return None

        position = self.positions[symbol]

        entry_price = position["entry_price"]

        quantity = position["quantity"]

        side = position["side"]

        # ------------------------------------------------------
        # Calculate PnL
        # ------------------------------------------------------

        if side == "BUY":

            pnl = (
                price - entry_price
            ) * quantity

        else:

            pnl = (
                entry_price - price
            ) * quantity

        pnl_percent = (
            pnl / position["capital"]
            if position["capital"] > 0
            else 0.0
        )

        # Return capital + profit/loss
        returned_capital = (
            position["capital"] + pnl
        )

        self.balance += returned_capital

        # ------------------------------------------------------
        # Trade record
        # ------------------------------------------------------

        trade = {
            "trade_id": str(uuid.uuid4()),
            "position_id": position["position_id"],
            "symbol": symbol,
            "side": side,
            "position_type": position["position_type"],
            "entry_price": entry_price,
            "exit_price": float(price),
            "quantity": quantity,
            "position_size": position["position_size"],
            "confidence": position["confidence"],
            "pnl": float(pnl),
            "pnl_percent": float(pnl_percent),
            "reason": reason,
            "entry_time": position["opened_at"],
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "metadata": position.get("metadata", {}),
        }

        self.trade_history.append(trade)

        self.total_realized_pnl += pnl

        self.total_trades += 1

        if pnl > 0:

            self.winning_trades += 1

        elif pnl < 0:

            self.losing_trades += 1

        # Order record
        close_side = (
            "SELL"
            if side == "BUY"
            else "BUY"
        )

        order = {
            "order_id": str(uuid.uuid4()),
            "position_id": position["position_id"],
            "symbol": symbol,
            "side": close_side,
            "action": "CLOSE",
            "price": float(price),
            "quantity": quantity,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "FILLED",
            "reason": reason,
        }

        self.order_history.append(order)

        # Remove active position
        del self.positions[symbol]

        logger.info(
            f"CLOSE {position['position_type']} | "
            f"{symbol} | "
            f"PnL=${pnl:.2f} ({pnl_percent:.2%}) | "
            f"Reason={reason}"
        )

        return trade.copy()

    # ==========================================================
    # PRICE UPDATE
    # ==========================================================

    def update_price(
        self,
        symbol: str,
        current_price: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Update current price and check SL/TP.
        """

        symbol = symbol.upper()

        if symbol not in self.positions:
            return None

        position = self.positions[symbol]

        pnl = self.calculate_unrealized_pnl(
            position,
            current_price
        )

        pnl_percent = (
            pnl / position["capital"]
            if position["capital"] > 0
            else 0.0
        )

        position["unrealized_pnl"] = pnl

        position["unrealized_pnl_percent"] = pnl_percent

        # ------------------------------------------------------
        # STOP LOSS
        # ------------------------------------------------------

        stop_loss = position.get("stop_loss")

        if stop_loss is not None:

            if position["side"] == "BUY":

                if current_price <= stop_loss:

                    return self.close_position(
                        symbol,
                        current_price,
                        "STOP_LOSS"
                    )

            elif position["side"] == "SELL":

                if current_price >= stop_loss:

                    return self.close_position(
                        symbol,
                        current_price,
                        "STOP_LOSS"
                    )

        # ------------------------------------------------------
        # TAKE PROFIT
        # ------------------------------------------------------

        take_profit = position.get("take_profit")

        if take_profit is not None:

            if position["side"] == "BUY":

                if current_price >= take_profit:

                    return self.close_position(
                        symbol,
                        current_price,
                        "TAKE_PROFIT"
                    )

            elif position["side"] == "SELL":

                if current_price <= take_profit:

                    return self.close_position(
                        symbol,
                        current_price,
                        "TAKE_PROFIT"
                    )

        return None

    # ==========================================================
    # PNL
    # ==========================================================

    @staticmethod
    def calculate_unrealized_pnl(
        position: Dict[str, Any],
        current_price: float,
    ) -> float:
        """Calculate unrealized PnL."""

        entry_price = position["entry_price"]

        quantity = position["quantity"]

        if position["side"] == "BUY":

            return (
                current_price - entry_price
            ) * quantity

        return (
            entry_price - current_price
        ) * quantity

    # ==========================================================
    # STATISTICS
    # ==========================================================

    def get_win_rate(self) -> float:

        if self.total_trades == 0:
            return 0.0

        return (
            self.winning_trades
            / self.total_trades
        )

    def get_summary(
        self,
        prices: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:

        prices = prices or {}

        unrealized_pnl = (
            self.get_total_unrealized_pnl(prices)
        )

        equity = (
            self.balance
            + unrealized_pnl
        )

        return {
            "mode": "paper",

            "initial_balance": self.initial_balance,

            "balance": round(
                self.balance,
                4
            ),

            "equity": round(
                equity,
                4
            ),

            "realized_pnl": round(
                self.total_realized_pnl,
                4
            ),

            "unrealized_pnl": round(
                unrealized_pnl,
                4
            ),

            "total_pnl": round(
                self.total_realized_pnl
                + unrealized_pnl,
                4
            ),

            "return_percent": round(
                (
                    (
                        equity
                        - self.initial_balance
                    )
                    / self.initial_balance
                )
                * 100,
                4
            ),

            "active_positions": len(
                self.positions
            ),

            "total_trades": self.total_trades,

            "winning_trades": (
                self.winning_trades
            ),

            "losing_trades": (
                self.losing_trades
            ),

            "win_rate": round(
                self.get_win_rate(),
                4
            ),

            "positions": list(
                self.positions.values()
            ),
        }

    # ==========================================================
    # HISTORY
    # ==========================================================

    def get_trade_history(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:

        return self.trade_history[-limit:]

    def get_order_history(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:

        return self.order_history[-limit:]

    def get_position(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:

        return self.positions.get(
            symbol.upper()
        )

    # ==========================================================
    # RESET
    # ==========================================================

    def reset(self):

        logger.warning(
            "RESETTING PAPER TRADING ENGINE"
        )

        self.balance = self.initial_balance

        self.positions.clear()

        self.trade_history.clear()

        self.order_history.clear()

        self.total_realized_pnl = 0.0

        self.total_trades = 0

        self.winning_trades = 0

        self.losing_trades = 0


# ==============================================================
# TEST
# ==============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    engine = PaperTradingEngine(
        initial_balance=10000
    )

    print("\n" + "=" * 70)
    print("PAPER TRADING ENGINE TEST")
    print("=" * 70)

    # ----------------------------------------------------------
    # TEST BUY
    # ----------------------------------------------------------

    print("\nTEST 1 — OPEN LONG")

    position = engine.open_position(
        symbol="BTC-USD",
        side="BUY",
        price=62760.21,
        position_size=0.08,
        confidence=0.78,
        stop_loss=61000,
        take_profit=65000,
        metadata={
            "source": "decision_engine",
            "strategy": "AI_SCALPING"
        }
    )

    print(position)

    # ----------------------------------------------------------
    # PRICE UPDATE
    # ----------------------------------------------------------

    print("\nTEST 2 — PRICE UPDATE")

    engine.update_price(
        "BTC-USD",
        64000
    )

    print(
        engine.get_summary(
            {"BTC-USD": 64000}
        )
    )

    # ----------------------------------------------------------
    # CLOSE
    # ----------------------------------------------------------

    print("\nTEST 3 — CLOSE LONG")

    trade = engine.close_position(
        "BTC-USD",
        64500,
        "MANUAL_TEST"
    )

    print(trade)

    # ----------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------

    print("\nTEST 4 — FINAL SUMMARY")

    print(
        engine.get_summary()
    )

    print("\nTRADE HISTORY")

    for trade in engine.get_trade_history():

        print(trade)
