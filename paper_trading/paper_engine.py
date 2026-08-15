"""
Paper Trading Engine v3

Tugas:
1. Menjalankan simulasi BUY / SELL
2. Mengelola LONG / SHORT position
3. Menghitung realized & unrealized PnL
4. Mengelola Stop Loss / Take Profit
5. Mengelola balance dan equity
6. Menyimpan trade history
7. Menyimpan order history
8. Menyediakan statistik trading
9. Tidak mengambil keputusan trading sendiri

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
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


logger = logging.getLogger(__name__)


class PaperTradingEngine:

    def __init__(
        self,
        initial_balance: float = 10000.0,
        max_position_size: float = 0.20,
    ):
        """
        Initialize Paper Trading Engine.

        Args:
            initial_balance:
                Modal awal simulasi.

            max_position_size:
                Maksimum persentase portfolio
                yang boleh digunakan dalam satu posisi.
        """

        # ------------------------------------------------------
        # NORMALIZE CONFIGURATION
        # ------------------------------------------------------

        # TradingIntegrationEngine kemungkinan mengirim
        # configuration dictionary.
        #
        # Contoh:
        #
        # PaperTradingEngine({
        #     "initial_balance": 10000,
        #     "max_position_size": 0.20
        # })
        #
        # Kita dukung format tersebut di sini tanpa
        # mengganggu penggunaan normal:
        #
        # PaperTradingEngine(10000)

        if isinstance(initial_balance, dict):

            config = initial_balance

            initial_balance = config.get(
                "initial_balance",
                10000.0,
            )

            max_position_size = config.get(
                "max_position_size",
                0.20,
            )

        # ------------------------------------------------------
        # CORE ACCOUNT
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

        # symbol -> position
        self.positions: Dict[
            str,
            Dict[str, Any]
        ] = {}

        # ------------------------------------------------------
        # HISTORY
        # ------------------------------------------------------

        self.trade_history: List[
            Dict[str, Any]
        ] = []

        self.order_history: List[
            Dict[str, Any]
        ] = []

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
    # TIME
    # ==========================================================

    @staticmethod
    def _utc_now() -> str:
        """
        Return timezone-aware UTC timestamp.
        """

        return datetime.now(
            timezone.utc
        ).isoformat()

    # ==========================================================
    # PORTFOLIO
    # ==========================================================

    def get_balance(self) -> float:
        """
        Return available cash balance.
        """

        return float(self.balance)

    def get_equity(
        self,
        prices: Optional[
            Dict[str, float]
        ] = None,
    ) -> float:
        """
        Return total portfolio equity.

        Equity =
            available balance
            + unrealized PnL
        """

        prices = prices or {}

        unrealized_pnl = (
            self.get_total_unrealized_pnl(
                prices
            )
        )

        return (
            self.balance
            + unrealized_pnl
        )

    def get_total_unrealized_pnl(
        self,
        prices: Dict[str, float],
    ) -> float:
        """
        Calculate unrealized PnL
        across all active positions.
        """

        total = 0.0

        for symbol, position in (
            self.positions.items()
        ):

            current_price = prices.get(
                symbol
            )

            if current_price is None:
                continue

            total += (
                self.calculate_unrealized_pnl(
                    position,
                    current_price,
                )
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
        metadata: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Open LONG or SHORT position.

        BUY  -> LONG
        SELL -> SHORT

        Example:

            position_size=0.08

        berarti menggunakan 8%
        dari equity sebagai capital posisi.
        """

        symbol = symbol.upper()

        side = side.upper()

        # ------------------------------------------------------
        # VALIDATION
        # ------------------------------------------------------

        if side not in (
            "BUY",
            "SELL",
        ):

            logger.warning(
                "Invalid side: %s",
                side,
            )

            return None

        try:

            price = float(price)

            position_size = float(
                position_size
            )

            confidence = float(
                confidence
            )

        except (
            TypeError,
            ValueError,
        ):

            logger.warning(
                "Invalid numeric input."
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

        if position_size > (
            self.max_position_size
        ):

            logger.warning(
                "Position size %.2f%% exceeds "
                "maximum %.2f%%",
                position_size * 100,
                self.max_position_size * 100,
            )

            return None

        # ------------------------------------------------------
        # ONE POSITION PER SYMBOL
        # ------------------------------------------------------

        if symbol in self.positions:

            logger.warning(
                "%s already has an active position.",
                symbol,
            )

            return None

        # ------------------------------------------------------
        # CAPITAL
        # ------------------------------------------------------

        equity = self.get_equity()

        capital = (
            equity * position_size
        )

        if capital <= 0:

            logger.warning(
                "Calculated position capital "
                "must be greater than zero."
            )

            return None

        if capital > self.balance:

            logger.warning(
                "Insufficient balance | "
                "Required=$%.2f | "
                "Balance=$%.2f",
                capital,
                self.balance,
            )

            return None

        quantity = (
            capital / price
        )

        # ------------------------------------------------------
        # POSITION
        # ------------------------------------------------------

        position_id = str(
            uuid.uuid4()
        )

        position_type = (
            "LONG"
            if side == "BUY"
            else "SHORT"
        )

        position = {

            "position_id":
                position_id,

            "symbol":
                symbol,

            "side":
                side,

            "position_type":
                position_type,

            "entry_price":
                float(price),

            "quantity":
                float(quantity),

            "capital":
                float(capital),

            "position_size":
                float(position_size),

            "confidence":
                float(confidence),

            "stop_loss":
                (
                    float(stop_loss)
                    if stop_loss is not None
                    else None
                ),

            "take_profit":
                (
                    float(take_profit)
                    if take_profit is not None
                    else None
                ),

            "opened_at":
                self._utc_now(),

            "metadata":
                metadata or {},

            "unrealized_pnl":
                0.0,

            "unrealized_pnl_percent":
                0.0,
        }

        # ------------------------------------------------------
        # RESERVE CAPITAL
        # ------------------------------------------------------

        self.balance -= capital

        self.positions[
            symbol
        ] = position

        # ------------------------------------------------------
        # ORDER HISTORY
        # ------------------------------------------------------

        order = {

            "order_id":
                str(uuid.uuid4()),

            "position_id":
                position_id,

            "symbol":
                symbol,

            "side":
                side,

            "action":
                "OPEN",

            "price":
                float(price),

            "quantity":
                float(quantity),

            "created_at":
                self._utc_now(),

            "status":
                "FILLED",
        }

        self.order_history.append(
            order
        )

        logger.info(
            "OPEN %s | %s | "
            "Qty=%.8f | Price=$%.2f",
            position_type,
            symbol,
            quantity,
            price,
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

        try:

            price = float(price)

        except (
            TypeError,
            ValueError,
        ):

            logger.warning(
                "Invalid closing price."
            )

            return None

        if price <= 0:

            logger.warning(
                "Closing price must be greater than zero."
            )

            return None

        # ------------------------------------------------------
        # CHECK POSITION
        # ------------------------------------------------------

        if symbol not in self.positions:

            logger.warning(
                "No active position for %s",
                symbol,
            )

            return None

        position = self.positions[
            symbol
        ]

        entry_price = (
            position["entry_price"]
        )

        quantity = (
            position["quantity"]
        )

        side = position["side"]

        # ------------------------------------------------------
        # CALCULATE PNL
        # ------------------------------------------------------

        if side == "BUY":

            pnl = (
                price - entry_price
            ) * quantity

        else:

            pnl = (
                entry_price - price
            ) * quantity

        capital = (
            position["capital"]
        )

        pnl_percent = (
            pnl / capital
            if capital > 0
            else 0.0
        )

        # ------------------------------------------------------
        # RETURN CAPITAL + PNL
        # ------------------------------------------------------

        returned_capital = (
            capital + pnl
        )

        self.balance += (
            returned_capital
        )

        # ------------------------------------------------------
        # TRADE RECORD
        # ------------------------------------------------------

        trade = {

            "trade_id":
                str(uuid.uuid4()),

            "position_id":
                position["position_id"],

            "symbol":
                symbol,

            "side":
                side,

            "position_type":
                position["position_type"],

            "entry_price":
                entry_price,

            "exit_price":
                float(price),

            "quantity":
                quantity,

            "position_size":
                position["position_size"],

            "confidence":
                position["confidence"],

            "pnl":
                float(pnl),

            "pnl_percent":
                float(pnl_percent),

            "reason":
                reason,

            "entry_time":
                position["opened_at"],

            "exit_time":
                self._utc_now(),

            "metadata":
                position.get(
                    "metadata",
                    {},
                ),
        }

        self.trade_history.append(
            trade
        )

        # ------------------------------------------------------
        # STATISTICS
        # ------------------------------------------------------

        self.total_realized_pnl += (
            pnl
        )

        self.total_trades += 1

        if pnl > 0:

            self.winning_trades += 1

        elif pnl < 0:

            self.losing_trades += 1

        # ------------------------------------------------------
        # CLOSE ORDER
        # ------------------------------------------------------

        close_side = (
            "SELL"
            if side == "BUY"
            else "BUY"
        )

        order = {

            "order_id":
                str(uuid.uuid4()),

            "position_id":
                position["position_id"],

            "symbol":
                symbol,

            "side":
                close_side,

            "action":
                "CLOSE",

            "price":
                float(price),

            "quantity":
                quantity,

            "created_at":
                self._utc_now(),

            "status":
                "FILLED",

            "reason":
                reason,
        }

        self.order_history.append(
            order
        )

        # ------------------------------------------------------
        # REMOVE POSITION
        # ------------------------------------------------------

        del self.positions[
            symbol
        ]

        logger.info(
            "CLOSE %s | %s | "
            "PnL=$%.2f (%.2f%%) | "
            "Reason=%s",
            position["position_type"],
            symbol,
            pnl,
            pnl_percent * 100,
            reason,
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
        Update current market price.

        Also checks:
            - Stop Loss
            - Take Profit

        If triggered, position is automatically closed.
        """

        symbol = symbol.upper()

        try:

            current_price = float(
                current_price
            )

        except (
            TypeError,
            ValueError,
        ):

            logger.warning(
                "Invalid current price."
            )

            return None

        if current_price <= 0:

            logger.warning(
                "Current price must be greater than zero."
            )

            return None

        if symbol not in self.positions:

            return None

        position = self.positions[
            symbol
        ]

        # ------------------------------------------------------
        # UNREALIZED PNL
        # ------------------------------------------------------

        pnl = (
            self.calculate_unrealized_pnl(
                position,
                current_price,
            )
        )

        capital = (
            position["capital"]
        )

        pnl_percent = (
            pnl / capital
            if capital > 0
            else 0.0
        )

        position[
            "unrealized_pnl"
        ] = float(pnl)

        position[
            "unrealized_pnl_percent"
        ] = float(pnl_percent)

        # ------------------------------------------------------
        # STOP LOSS
        # ------------------------------------------------------

        stop_loss = (
            position.get(
                "stop_loss"
            )
        )

        if stop_loss is not None:

            if position["side"] == "BUY":

                if current_price <= stop_loss:

                    return self.close_position(
                        symbol,
                        current_price,
                        "STOP_LOSS",
                    )

            else:

                if current_price >= stop_loss:

                    return self.close_position(
                        symbol,
                        current_price,
                        "STOP_LOSS",
                    )

        # ------------------------------------------------------
        # TAKE PROFIT
        # ------------------------------------------------------

        take_profit = (
            position.get(
                "take_profit"
            )
        )

        if take_profit is not None:

            if position["side"] == "BUY":

                if current_price >= take_profit:

                    return self.close_position(
                        symbol,
                        current_price,
                        "TAKE_PROFIT",
                    )

            else:

                if current_price <= take_profit:

                    return self.close_position(
                        symbol,
                        current_price,
                        "TAKE_PROFIT",
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
        """
        Calculate unrealized PnL.
        """

        entry_price = float(
            position["entry_price"]
        )

        quantity = float(
            position["quantity"]
        )

        current_price = float(
            current_price
        )

        if position["side"] == "BUY":

            return (
                current_price
                - entry_price
            ) * quantity

        return (
            entry_price
            - current_price
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

    # ==========================================================
    # SUMMARY
    # ==========================================================

    def get_summary(
        self,
        prices: Optional[
            Dict[str, float]
        ] = None,
    ) -> Dict[str, Any]:

        prices = prices or {}

        unrealized_pnl = (
            self.get_total_unrealized_pnl(
                prices
            )
        )

        equity = (
            self.balance
            + unrealized_pnl
        )

        total_pnl = (
            self.total_realized_pnl
            + unrealized_pnl
        )

        return {

            "mode":
                "paper",

            "initial_balance":
                round(
                    self.initial_balance,
                    4,
                ),

            "balance":
                round(
                    self.balance,
                    4,
                ),

            "equity":
                round(
                    equity,
                    4,
                ),

            "realized_pnl":
                round(
                    self.total_realized_pnl,
                    4,
                ),

            "unrealized_pnl":
                round(
                    unrealized_pnl,
                    4,
                ),

            "total_pnl":
                round(
                    total_pnl,
                    4,
                ),

            "return_percent":
                round(
                    (
                        (
                            equity
                            - self.initial_balance
                        )
                        / self.initial_balance
                    )
                    * 100,
                    4,
                ),

            "active_positions":
                len(
                    self.positions
                ),

            "total_trades":
                self.total_trades,

            "winning_trades":
                self.winning_trades,

            "losing_trades":
                self.losing_trades,

            "win_rate":
                round(
                    self.get_win_rate(),
                    4,
                ),

            "positions":
                [
                    position.copy()
                    for position
                    in self.positions.values()
                ],
        }

    # ==========================================================
    # HISTORY
    # ==========================================================

    def get_trade_history(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:

        if limit <= 0:

            return []

        return self.trade_history[
            -limit:
        ]

    def get_order_history(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:

        if limit <= 0:

            return []

        return self.order_history[
            -limit:
        ]

    # ==========================================================
    # POSITION
    # ==========================================================

    def get_position(
        self,
        symbol: str,
    ) -> Optional[Dict[str, Any]]:

        position = self.positions.get(
            symbol.upper()
        )

        if position is None:

            return None

        return position.copy()

    # ==========================================================
    # RESET
    # ==========================================================

    def reset(self):
        """
        Reset entire paper trading account.
        """

        logger.warning(
            "RESETTING PAPER TRADING ENGINE"
        )

        self.balance = (
            self.initial_balance
        )

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
        level=logging.INFO,
        format=(
            "%(levelname)s:"
            "%(name)s:"
            "%(message)s"
        ),
    )

    engine = PaperTradingEngine(
        initial_balance=10000.0,
        max_position_size=0.20,
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "PAPER TRADING ENGINE TEST"
    )

    print(
        "=" * 70
    )

    # ==========================================================
    # TEST 1 — OPEN LONG
    # ==========================================================

    print(
        "\nTEST 1 — OPEN LONG"
    )

    position = engine.open_position(

        symbol="BTC-USD",

        side="BUY",

        price=62760.21,

        position_size=0.08,

        confidence=0.78,

        stop_loss=61000,

        take_profit=65000,

        metadata={
            "source":
                "decision_engine",

            "strategy":
                "AI_SCALPING",
        },
    )

    print(position)

    # ==========================================================
    # TEST 2 — PRICE UPDATE
    # ==========================================================

    print(
        "\nTEST 2 — PRICE UPDATE"
    )

    engine.update_price(
        "BTC-USD",
        64000,
    )

    print(
        engine.get_summary(
            {
                "BTC-USD":
                    64000,
            }
        )
    )

    # ==========================================================
    # TEST 3 — CLOSE LONG
    # ==========================================================

    print(
        "\nTEST 3 — CLOSE LONG"
    )

    trade = engine.close_position(
        "BTC-USD",
        64500,
        "MANUAL_TEST",
    )

    print(trade)

    # ==========================================================
    # TEST 4 — FINAL SUMMARY
    # ==========================================================

    print(
        "\nTEST 4 — FINAL SUMMARY"
    )

    print(
        engine.get_summary()
    )

    # ==========================================================
    # TEST 5 — SHORT
    # ==========================================================

    print(
        "\nTEST 5 — OPEN SHORT"
    )

    short_position = (
        engine.open_position(

            symbol="BTC-USD",

            side="SELL",

            price=64500,

            position_size=0.07,

            confidence=0.81,

            stop_loss=66000,

            take_profit=62000,

            metadata={
                "source":
                    "decision_engine",

                "strategy":
                    "AI_SCALPING",
            },
        )
    )

    print(short_position)

    # ==========================================================
    # TEST 6 — SHORT PROFIT
    # ==========================================================

    print(
        "\nTEST 6 — CLOSE SHORT"
    )

    short_trade = (
        engine.close_position(
            "BTC-USD",
            63000,
            "MANUAL_SHORT_TEST",
        )
    )

    print(short_trade)

    # ==========================================================
    # FINAL SUMMARY
    # ==========================================================

    print(
        "\nFINAL SUMMARY"
    )

    print(
        engine.get_summary()
    )

    # ==========================================================
    # TRADE HISTORY
    # ==========================================================

    print(
        "\nTRADE HISTORY"
    )

    for trade in (
        engine.get_trade_history()
    ):

        print(trade)

    print(
        "\n"
        + "=" * 70
    )

    print(
        "PAPER ENGINE TEST COMPLETE"
    )

    print(
        "=" * 70
    )
