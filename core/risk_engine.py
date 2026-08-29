"""Deterministic portfolio risk gate.

Risk evaluates an already-created trading candidate. It never predicts direction
and never changes BUY into SELL (or vice versa).
"""
from __future__ import annotations
import logging, math
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class RiskDecision:
    approved: bool
    symbol: str
    action: str
    original_confidence: float
    adjusted_confidence: float
    requested_position_size: float
    approved_position_size: float
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float
    exposure: float
    reason: str
    risk_score: float
    timestamp: datetime
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self); data["timestamp"] = self.timestamp.isoformat(); return data

class RiskEngine:
    """Pure deterministic approval layer. It does not generate signals."""
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.initial_capital = float(cfg.get("initial_capital", 10_000_000.0))
        self.current_capital = float(cfg.get("current_capital", self.initial_capital))
        self.max_position_size = float(cfg.get("max_position_size", 0.20))
        self.max_total_exposure = float(cfg.get("max_total_exposure", 0.50))
        self.max_open_positions = min(3, max(1, int(cfg.get("max_open_positions", 3))))
        self.minimum_confidence = float(cfg.get("minimum_confidence", 0.55))
        self.high_confidence = float(cfg.get("high_confidence", 0.75))
        self.max_risk_per_trade = float(cfg.get("max_risk_per_trade", 0.01))
        self.max_daily_loss = float(cfg.get("max_daily_loss", 0.03))
        self.minimum_risk_reward = float(cfg.get("minimum_risk_reward", 1.5))
        self.max_volatility = float(cfg.get("max_volatility", 0.08))
        self.daily_pnl = 0.0; self.open_positions = 0; self.current_exposure = 0.0
        self.last_decision_time = None; self.total_evaluations = 0; self.approved_trades = 0; self.rejected_trades = 0

    def evaluate(self, symbol: str, action: str, confidence: float, position_size: float,
                 entry_price: float, stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
                 volatility: Optional[float] = None, current_exposure: Optional[float] = None,
                 open_positions: Optional[int] = None, daily_pnl: Optional[float] = None) -> RiskDecision:
        self.total_evaluations += 1
        action = str(action).upper(); confidence = self._clamp(confidence, 0, 1)
        requested_size = self._clamp(position_size, 0, self.max_position_size)
        entry_price = float(entry_price or 0); volatility = float(volatility or 0)
        exposure = float(self.current_exposure if current_exposure is None else current_exposure)
        positions = int(self.open_positions if open_positions is None else open_positions)
        daily_loss = float(self.daily_pnl if daily_pnl is None else daily_pnl)
        if action not in {"BUY", "SELL", "STRONG_BUY", "STRONG_SELL"}:
            return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "NO_EXECUTION_CANDIDATE")
        if entry_price <= 0: return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "INVALID_ENTRY_PRICE")
        if confidence < self.minimum_confidence: return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "CONFIDENCE_BELOW_RISK_MINIMUM")
        if daily_loss <= -self.max_daily_loss: return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "DAILY_LOSS_LIMIT_REACHED")
        # Position count is an entry constraint. SELL closes an existing spot long.
        if action in {"BUY", "STRONG_BUY"} and positions >= self.max_open_positions:
            return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "MAX_OPEN_POSITIONS")
        if action in {"BUY", "STRONG_BUY"} and exposure + requested_size > self.max_total_exposure:
            requested_size = max(0.0, self.max_total_exposure - exposure)
        if requested_size <= 0.001: return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "POSITION_SIZE_TOO_SMALL")
        if volatility > self.max_volatility:
            requested_size *= self._clamp(self.max_volatility / volatility, 0.25, 1.0)
        adjusted_size = min(requested_size * self._confidence_factor(confidence), self.max_position_size)
        if adjusted_size <= 0.001: return self._reject(symbol, action, confidence, requested_size, entry_price, stop_loss, take_profit, "ADJUSTED_POSITION_TOO_SMALL")
        risk_amount, reward_amount, rr = self._calculate_risk_reward(action, entry_price, stop_loss, take_profit)
        if stop_loss is not None and take_profit is not None and rr < self.minimum_risk_reward:
            return self._reject(symbol, action, confidence, adjusted_size, entry_price, stop_loss, take_profit, f"RISK_REWARD_BELOW_MINIMUM:{rr:.2f}")
        self.approved_trades += 1; self.last_decision_time = datetime.now()
        return RiskDecision(True, symbol, action, confidence, confidence * self._confidence_factor(confidence), requested_size,
                            adjusted_size, entry_price, stop_loss, take_profit, risk_amount, reward_amount, rr,
                            exposure + adjusted_size, "RISK_CHECKS_PASSED", self._calculate_risk_score(confidence, volatility, rr), datetime.now())

    def _reject(self, symbol, action, confidence, size, entry, sl, tp, reason):
        self.rejected_trades += 1
        return RiskDecision(False, symbol, action, confidence, confidence, size, 0.0, entry, sl, tp, 0.0, 0.0, 0.0,
                            self.current_exposure, reason, 0.0, datetime.now())

    @staticmethod
    def _clamp(v, lo, hi): return max(lo, min(hi, float(v)))
    def _confidence_factor(self, c):
        if c < self.minimum_confidence: return 0.0
        if c >= self.high_confidence: return 1.0
        span = self.high_confidence - self.minimum_confidence
        return 1.0 if span <= 0 else (c - self.minimum_confidence) / span
    @staticmethod
    def _calculate_risk_reward(action, entry, sl, tp):
        if sl is None or tp is None: return 0.0, 0.0, 0.0
        if action in {"BUY", "STRONG_BUY"}:
            risk=max(0.0, entry-sl); reward=max(0.0, tp-entry)
        else:
            risk=max(0.0, sl-entry); reward=max(0.0, entry-tp)
        return risk, reward, reward/risk if risk>0 else 0.0
    @staticmethod
    def _calculate_risk_score(confidence, volatility, rr):
        return max(0.0, min(1.0, confidence*0.6 + min(rr/3.0,1.0)*0.25 + max(0.0,1-volatility/0.08)*0.15))
