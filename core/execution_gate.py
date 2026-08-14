"""
Execution Gate
==============

Gerbang terakhir sebelum keputusan trading diteruskan
ke Executor.

Prinsip:
    Decision Engine = otak keputusan
    Execution Gate  = security gate
    Executor        = tangan yang melakukan order

Order hanya boleh diteruskan jika:
    1. Decision APPROVE
    2. approved == True
    3. execution_allowed == True
    4. action valid
    5. position_size > 0
    6. confidence memenuhi minimum
    7. risk/reward memenuhi minimum
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


@dataclass
class ExecutionGateResult:
    timestamp: datetime

    symbol: str

    allowed: bool

    action: str

    position_size: float

    confidence: float

    reason: str

    checks: Dict[str, bool]

    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)

        data["timestamp"] = self.timestamp.isoformat()

        return data


class ExecutionGate:
    """
    Security layer sebelum Executor.

    Gate ini TIDAK membuat keputusan BUY/SELL.

    Gate hanya menentukan:
        "Boleh dieksekusi atau tidak?"
    """

    VALID_ACTIONS = {
        "BUY",
        "SELL",
    }

def __init__(
    self,
    min_confidence: float = 0.60,
    min_risk_reward: float = 1.50,
    max_position_size: float = 0.20,
    require_approved: bool = True,
    require_execution_allowed: bool = True,
):
    """
    Initialize Execution Gate.

    Supports two formats:

    1. Direct arguments:

        ExecutionGate(
            min_confidence=0.60,
            min_risk_reward=1.50,
            max_position_size=0.20
        )

    2. Configuration dictionary:

        ExecutionGate({
            "min_confidence": 0.60,
            "min_risk_reward": 1.50,
            "max_position_size": 0.20
        })
    """

    # ------------------------------------------------------
    # SUPPORT CONFIG DICTIONARY
    # ------------------------------------------------------

    if isinstance(min_confidence, dict):

        config = min_confidence

        min_confidence = config.get(
            "min_confidence",
            0.60
        )

        min_risk_reward = config.get(
            "min_risk_reward",
            1.50
        )

        max_position_size = config.get(
            "max_position_size",
            0.20
        )

        require_approved = config.get(
            "require_approved",
            True
        )

        require_execution_allowed = config.get(
            "require_execution_allowed",
            True
        )

    # ------------------------------------------------------
    # NORMALIZE VALUES
    # ------------------------------------------------------

    self.min_confidence = float(
        min_confidence
    )

    self.min_risk_reward = float(
        min_risk_reward
    )

    self.max_position_size = float(
        max_position_size
    )

    self.require_approved = bool(
        require_approved
    )

    self.require_execution_allowed = bool(
        require_execution_allowed
    )

    logger.info(
        "Execution Gate initialized | "
        "min_confidence=%.2f | "
        "min_rr=%.2f | "
        "max_position=%.2f",
        self.min_confidence,
        self.min_risk_reward,
        self.max_position_size,
    )
    # ==========================================================
    # MAIN GATE
    # ==========================================================

    def evaluate(
        self,
        decision: Dict[str, Any]
    ) -> ExecutionGateResult:

        symbol = decision.get("symbol", "UNKNOWN")

        action = str(
            decision.get("action", "HOLD")
        ).upper()

        approved = bool(
            decision.get("approved", False)
        )

        execution_allowed = bool(
            decision.get("execution_allowed", False)
        )

        confidence = float(
            decision.get("confidence", 0.0)
        )

        position_size = float(
            decision.get("position_size", 0.0)
        )

        risk_reward_ratio = float(
            decision.get("risk_reward_ratio", 0.0)
        )

        logger.info(
            "Execution Gate evaluating %s | action=%s",
            symbol,
            action
        )

        # ------------------------------------------------------
        # HOLD
        # ------------------------------------------------------

        if action == "HOLD":

            return self._blocked(
                symbol=symbol,
                action=action,
                position_size=0.0,
                confidence=confidence,
                reason="HOLD action cannot be executed.",
                checks={
                    "approved": approved,
                    "execution_allowed": execution_allowed,
                    "valid_action": False,
                    "confidence": confidence >= self.min_confidence,
                    "risk_reward": False,
                    "position_size": False,
                }
            )

        # ------------------------------------------------------
        # VALID ACTION
        # ------------------------------------------------------

        valid_action = action in self.VALID_ACTIONS

        if not valid_action:

            return self._blocked(
                symbol=symbol,
                action=action,
                position_size=position_size,
                confidence=confidence,
                reason=f"Invalid execution action: {action}",
                checks={
                    "approved": approved,
                    "execution_allowed": execution_allowed,
                    "valid_action": False,
                    "confidence": False,
                    "risk_reward": False,
                    "position_size": False,
                }
            )

        # ------------------------------------------------------
        # APPROVAL CHECK
        # ------------------------------------------------------

        approved_check = (
            approved
            if self.require_approved
            else True
        )

        # ------------------------------------------------------
        # EXECUTION PERMISSION
        # ------------------------------------------------------

        execution_check = (
            execution_allowed
            if self.require_execution_allowed
            else True
        )

        # ------------------------------------------------------
        # CONFIDENCE
        # ------------------------------------------------------

        confidence_check = (
            confidence >= self.min_confidence
        )

        # ------------------------------------------------------
        # RISK / REWARD
        # ------------------------------------------------------

        risk_reward_check = (
            risk_reward_ratio >= self.min_risk_reward
        )

        # ------------------------------------------------------
        # POSITION SIZE
        # ------------------------------------------------------

        position_size_check = (
            position_size > 0
            and position_size <= self.max_position_size
        )

        checks = {
            "approved": approved_check,
            "execution_allowed": execution_check,
            "valid_action": valid_action,
            "confidence": confidence_check,
            "risk_reward": risk_reward_check,
            "position_size": position_size_check,
        }

        # ------------------------------------------------------
        # FINAL DECISION
        # ------------------------------------------------------

        allowed = all(checks.values())

        if not allowed:

            failed_checks = [
                name
                for name, passed in checks.items()
                if not passed
            ]

            reason = (
                "Execution blocked. Failed checks: "
                + ", ".join(failed_checks)
            )

            logger.warning(
                "%s | %s",
                symbol,
                reason
            )

            return self._blocked(
                symbol=symbol,
                action=action,
                position_size=position_size,
                confidence=confidence,
                reason=reason,
                checks=checks
            )

        # ------------------------------------------------------
        # ALLOWED
        # ------------------------------------------------------

        reason = (
            "Execution approved. "
            "All execution-gate checks passed."
        )

        logger.info(
            "EXECUTION ALLOWED | %s | %s | %.2f%%",
            symbol,
            action,
            position_size * 100
        )

        return ExecutionGateResult(
            timestamp=datetime.now(),
            symbol=symbol,
            allowed=True,
            action=action,
            position_size=position_size,
            confidence=confidence,
            reason=reason,
            checks=checks,
            metadata={
                "risk_reward_ratio": risk_reward_ratio,
                "max_position_size": self.max_position_size,
                "min_confidence": self.min_confidence,
                "min_risk_reward": self.min_risk_reward,
            }
        )

    # ==========================================================
    # BLOCK HELPER
    # ==========================================================

    def _blocked(
        self,
        symbol: str,
        action: str,
        position_size: float,
        confidence: float,
        reason: str,
        checks: Dict[str, bool],
    ) -> ExecutionGateResult:

        logger.warning(
            "EXECUTION BLOCKED | %s | %s | %s",
            symbol,
            action,
            reason
        )

        return ExecutionGateResult(
            timestamp=datetime.now(),
            symbol=symbol,
            allowed=False,
            action="HOLD",
            position_size=0.0,
            confidence=confidence,
            reason=reason,
            checks=checks,
            metadata={
                "original_action": action,
                "blocked": True,
            }
        )


# ==============================================================
# TEST
# ==============================================================

if __name__ == "__main__":

    import json

    logging.basicConfig(
        level=logging.INFO
    )

    gate = ExecutionGate()

    # ----------------------------------------------------------
    # TEST 1 — VALID BUY
    # ----------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("TEST 1 — VALID BUY")
    print("=" * 70)

    buy_decision = {
        "symbol": "BTC-USD",
        "decision": "APPROVE",
        "action": "BUY",
        "confidence": 0.78,
        "position_size": 0.08,
        "risk_reward_ratio": 2.4,
        "approved": True,
        "execution_allowed": True,
    }

    result = gate.evaluate(buy_decision)

    print(
        json.dumps(
            result.to_dict(),
            indent=2
        )
    )

    # ----------------------------------------------------------
    # TEST 2 — BLOCKED
    # ----------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("TEST 2 — EXECUTION DISABLED")
    print("=" * 70)

    blocked_decision = {
        "symbol": "BTC-USD",
        "decision": "APPROVE",
        "action": "BUY",
        "confidence": 0.78,
        "position_size": 0.08,
        "risk_reward_ratio": 2.4,
        "approved": True,
        "execution_allowed": False,
    }

    result = gate.evaluate(blocked_decision)

    print(
        json.dumps(
            result.to_dict(),
            indent=2
        )
    )

    # ----------------------------------------------------------
    # TEST 3 — HOLD
    # ----------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("TEST 3 — HOLD")
    print("=" * 70)

    hold_decision = {
        "symbol": "BTC-USD",
        "decision": "REJECT",
        "action": "HOLD",
        "confidence": 0.52,
        "position_size": 0.0,
        "risk_reward_ratio": 0.0,
        "approved": False,
        "execution_allowed": False,
    }

    result = gate.evaluate(hold_decision)

    print(
        json.dumps(
            result.to_dict(),
            indent=2
        )
    )
