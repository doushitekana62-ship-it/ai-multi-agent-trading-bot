"""Diagnostics for distinguishing normal HOLD from pipeline failure."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class HoldDiagnostics:
    consecutive_hold: int = 0
    consecutive_no_edge: int = 0
    consecutive_missing_movement: int = 0
    consecutive_ai_degraded: int = 0
    last_score: Optional[float] = None
    repeated_score_count: int = 0

    def observe(self, *, action: str, cycle_status: str, movement_available: bool = True, ai_degraded: bool = False, score: float = 0.0) -> Optional[str]:
        if str(action).upper() == "HOLD": self.consecutive_hold += 1
        else: self.consecutive_hold = 0
        if cycle_status == "NO_EDGE": self.consecutive_no_edge += 1
        else: self.consecutive_no_edge = 0
        if movement_available: self.consecutive_missing_movement = 0
        else: self.consecutive_missing_movement += 1
        if ai_degraded: self.consecutive_ai_degraded += 1
        else: self.consecutive_ai_degraded = 0
        if self.last_score is not None and abs(float(score) - self.last_score) < 1e-9: self.repeated_score_count += 1
        else: self.repeated_score_count = 0
        self.last_score = float(score)
        if self.consecutive_missing_movement >= 10: return "DATA_PROBLEM: short-horizon movement missing for 10 consecutive cycles"
        if self.consecutive_ai_degraded >= 10: return "AI_DEGRADED: external AI unavailable for 10 consecutive cycles"
        if self.repeated_score_count >= 10: return "PIPELINE_ANOMALY: identical decision score repeated for 10 consecutive cycles"
        if self.consecutive_hold >= 10: return "NO-TRADE ANOMALY: 10 consecutive HOLD cycles; inspect NO_EDGE vs DATA/RISK/POSITION state"
        return None
