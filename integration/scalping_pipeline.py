"""Safe scalping pipeline adapter.

Bridges the stateful scalping exit rules into the existing paper execution
pipeline without creating a second position ledger or bypassing entry controls.
The adapter only acts on an already-open BUY/LONG position. It never opens a
position and never creates a short position.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from core.scalping_controller import ScalpingController
from paper_trading.paper_engine import PaperTradingEngine


class ScalpingPipelineAdapter:
    """Apply stateful scalping exit policy to the pipeline's paper engine."""

    def __init__(
        self,
        paper_engine: PaperTradingEngine,
        controller: Optional[ScalpingController] = None,
    ) -> None:
        self.paper_engine = paper_engine
        self.controller = controller or ScalpingController()

    def evaluate_existing_long_exit(
        self,
        *,
        symbol: str,
        price: float,
        technical: float,
        sentiment: float,
        forecast: float,
        mimic: float,
        decision: float = 0.0,
        volatility: float = 0.02,
        data_quality: float = 1.0,
        prices: Optional[Sequence[float]] = None,
        volumes: Optional[Sequence[float]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Close an existing BUY position when dedicated exit evidence fires.

        Returns the paper trade record when a close occurs, otherwise ``None``.
        SL/TP handling remains owned by ``PaperTradingEngine.update_price`` and
        is intentionally not duplicated here.
        """
        position = self.paper_engine.get_position(symbol)
        if not position or str(position.get("side", "")).upper() != "BUY":
            return None

        should_exit, signal = self.controller.should_exit_long(
            technical=technical,
            sentiment=sentiment,
            forecast=forecast,
            mimic=mimic,
            decision=decision,
            volatility=volatility,
            data_quality=data_quality,
            prices=prices,
            volumes=volumes,
        )
        if not should_exit:
            return None

        trade = self.paper_engine.close_position(
            symbol=symbol,
            price=float(price),
            reason="DEDICATED_LONG_EXIT",
        )
        if trade is None:
            return None

        trade = dict(trade)
        trade["exit_signal"] = signal
        trade["exit_source"] = "scalping_pipeline_adapter"
        return trade
