"""Canonical analytical signal contract.

Analysts produce evidence; only the trader/decision layer produces an action.
Missing data is represented explicitly and never coerced into HOLD.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


class SignalDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SignalStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class CycleStatus(str, Enum):
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    DATA_STALE = "DATA_STALE"
    AI_DEGRADED = "AI_DEGRADED"
    ANALYZED = "ANALYZED"
    NO_EDGE = "NO_EDGE"
    HOLD_EXISTING_POSITION = "HOLD_EXISTING_POSITION"
    RISK_REJECTED = "RISK_REJECTED"
    EXECUTED = "EXECUTED"


@dataclass
class AnalyticalSignal:
    """Evidence returned by a specialist agent."""
    agent: str
    symbol: str
    direction: str = SignalDirection.NEUTRAL.value
    score: float = 0.0
    confidence: float = 0.0
    timeframe: str = "1m"
    evidence: List[str] = field(default_factory=list)
    data_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_age_seconds: float = 0.0
    status: str = SignalStatus.OK.value
    limitations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).upper()
        self.direction = str(self.direction).upper()
        if self.direction not in {x.value for x in SignalDirection}:
            self.direction = SignalDirection.NEUTRAL.value
        self.score = max(-1.0, min(1.0, float(self.score)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.status = str(self.status).upper()
        if self.status not in {x.value for x in SignalStatus}:
            self.status = SignalStatus.DEGRADED.value

    def usable(self) -> bool:
        return self.status == SignalStatus.OK.value and self.confidence > 0.0

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["data_timestamp"] = self.data_timestamp.isoformat()
        return value


def movement_score(value: Any, scale: float = 20.0) -> float:
    """Normalize a fractional return into [-1, 1]."""
    try:
        return max(-1.0, min(1.0, float(value) * scale))
    except (TypeError, ValueError):
        return 0.0


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else default
    except (TypeError, ValueError):
        return default


def utc_age_seconds(timestamp: Any) -> float:
    try:
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())
    except (TypeError, ValueError):
        return float("inf")
