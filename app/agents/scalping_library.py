from __future__ import annotations

from .signal_engine import SignalDecision, SignalEngine


class ScalpingLibrary:
    """Legacy validation layer kept separate from the Freqtrade executor."""

    def __init__(self, min_score: float = 70.0, fee_percent: float = 0.3, slippage_percent: float = 0.05) -> None:
        self.engine = SignalEngine(
            min_score=min_score,
            fee_percent=fee_percent,
            slippage_percent=slippage_percent,
        )

    def evaluate(self, **kwargs) -> SignalDecision:
        return self.engine.evaluate(**kwargs)
