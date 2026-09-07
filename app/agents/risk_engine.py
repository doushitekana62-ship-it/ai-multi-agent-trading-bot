from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    risk_multiplier: float
    reasons: list[str]


class RiskEngine:
    """Deterministic risk gate reusable by execution layers."""

    def __init__(
        self,
        daily_loss_limit_percent=3.0,
        max_drawdown_percent=5.0,
        max_total_open_risk_percent=1.5,
        max_loss_streak=3,
        cooldown_minutes=30,
    ):
        self.daily_loss_limit_percent = daily_loss_limit_percent
        self.max_drawdown_percent = max_drawdown_percent
        self.max_total_open_risk_percent = max_total_open_risk_percent
        self.max_loss_streak = max_loss_streak
        self.cooldown_minutes = cooldown_minutes

    def evaluate(
        self,
        daily_pnl: float,
        daily_start_balance: float,
        equity: float,
        peak_equity: float,
        open_risk_percent: float,
        loss_streak: int,
        cooldown_until: str | None = None,
        pair_quarantined: bool = False,
        spread_percent: float = 0.0,
    ) -> RiskDecision:
        reasons: list[str] = []
        if daily_start_balance <= 0 or equity <= 0:
            return RiskDecision(False, 0.0, ["invalid_equity"])

        daily_loss_pct = max(0.0, -daily_pnl / daily_start_balance * 100)
        drawdown_pct = max(0.0, (peak_equity - equity) / peak_equity * 100) if peak_equity > 0 else 0.0
        if daily_loss_pct >= self.daily_loss_limit_percent:
            reasons.append("daily_loss_limit")
        if drawdown_pct >= self.max_drawdown_percent:
            reasons.append("max_drawdown")
        if open_risk_percent >= self.max_total_open_risk_percent:
            reasons.append("total_open_risk")
        if loss_streak >= self.max_loss_streak:
            reasons.append("loss_streak")
        if pair_quarantined:
            reasons.append("pair_quarantine")
        if cooldown_until:
            try:
                until = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
                if until > datetime.now(timezone.utc):
                    reasons.append("cooldown")
            except ValueError:
                reasons.append("invalid_cooldown")
        if reasons:
            return RiskDecision(False, 0.0, reasons)

        multiplier = 1.0
        if drawdown_pct >= 3.0:
            multiplier *= 0.5
        elif drawdown_pct >= 1.5:
            multiplier *= 0.75
        if loss_streak == 2:
            multiplier *= 0.5
        if spread_percent >= 0.25:
            multiplier *= 0.75
        return RiskDecision(True, round(max(0.25, multiplier), 4), ["risk_gates_passed"])
