from dataclasses import dataclass


@dataclass(frozen=True)
class SignalDecision:
    action: str
    score: float
    expected_edge_percent: float
    reasons: list[str]
    features: dict


class SignalEngine:
    """Combine forecast, regime, microstructure and execution quality."""

    def __init__(self, min_score: float = 70.0, fee_percent: float = 0.3, slippage_percent: float = 0.05):
        self.min_score = min_score
        self.fee_percent = fee_percent
        self.slippage_percent = slippage_percent

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def evaluate(
        self,
        forecast,
        regime,
        spread_percent: float,
        book_imbalance: float,
        btc_return_percent: float,
        liquidity_score: float,
        support_resistance_score: float,
        data_quality: float,
        cooldown: bool = False,
        exposure_available: bool = True,
    ) -> SignalDecision:
        if forecast is None or regime is None:
            return SignalDecision("NO_TRADE", 0.0, -999.0, ["insufficient_data"], {})

        trend = 1.0 if regime.name == "TREND_UP" and forecast.action == "buy" else 0.0
        orderflow = self._clamp(0.5 + book_imbalance * 0.5)
        momentum = self._clamp(0.5 + float(forecast.indicators.get("momentum_percent", 0)) / 2)
        volume = self._clamp(liquidity_score)
        btc = self._clamp(0.5 + btc_return_percent / 2)
        sr = self._clamp(support_resistance_score)
        spread_quality = self._clamp(1.0 - max(0.0, spread_percent) / 0.5)
        score = 100 * (
            0.20 * trend
            + 0.20 * orderflow
            + 0.15 * momentum
            + 0.15 * volume
            + 0.15 * btc
            + 0.10 * sr
            + 0.05 * spread_quality
        )

        tp_percent = max(0.0, (forecast.suggested_tp / forecast.price - 1) * 100)
        expected_edge = tp_percent * (score / 100) - (
            2 * self.fee_percent + spread_percent + 2 * self.slippage_percent
        )

        failures: list[str] = []
        if regime.name in {"DATA_UNSAFE", "TREND_DOWN", "HIGH_VOLATILITY"}:
            failures.append(f"regime:{regime.name}")
        if data_quality < 0.7:
            failures.append("data_quality")
        if spread_percent > 0.5:
            failures.append("spread")
        if cooldown:
            failures.append("cooldown")
        if not exposure_available:
            failures.append("exposure")
        if expected_edge <= 0:
            failures.append("negative_expected_edge")

        if failures:
            action = "NO_TRADE"
            reasons = failures
        elif forecast.action == "buy" and score >= self.min_score:
            action = "OPEN"
            reasons = ["all_gates_passed"]
        else:
            action = "WAIT"
            reasons = ["score_below_threshold"]

        return SignalDecision(
            action,
            round(score, 2),
            round(expected_edge, 4),
            reasons,
            {
                "trend": trend,
                "orderflow": orderflow,
                "momentum": momentum,
                "volume": volume,
                "btc_lead": btc,
                "support_resistance": sr,
                "execution_quality": spread_quality,
                "spread_percent": spread_percent,
                "book_imbalance": book_imbalance,
                "btc_return_percent": btc_return_percent,
                "data_quality": data_quality,
            },
        )
