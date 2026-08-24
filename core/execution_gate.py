"""
Execution Gate
==============

Security gate terakhir sebelum keputusan trading
diteruskan ke Paper Trading Engine.

Flow:

    Decision Engine
          ↓
    Execution Gate
          ↓
    Paper Trading Engine

Execution Gate TIDAK membuat keputusan BUY/SELL.
Ia hanya memeriksa apakah keputusan yang sudah dibuat
boleh diteruskan untuk eksekusi.

Safety:
    - Default tidak mengizinkan execution jika flag tidak diberikan.
    - Gate hanya mendukung BUY / SELL.
    - HOLD selalu diblokir.
    - Position size dibatasi.
    - Confidence harus memenuhi minimum.
    - Risk/reward harus memenuhi minimum.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


# ==============================================================
# RESULT
# ==============================================================

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


# ==============================================================
# EXECUTION GATE
# ==============================================================

class ExecutionGate:

    """
    Security layer sebelum executor.

    Gate tidak menentukan arah pasar.

    Gate hanya menjawab:

        "Boleh dieksekusi atau tidak?"
    """

    VALID_ACTIONS = {
        "BUY",
        "SELL",
    }

    # ==========================================================
    # INITIALIZATION
    # ==========================================================

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

        Bisa dipanggil dengan:

        1. Dictionary

            ExecutionGate({
                "min_confidence": 0.60,
                "min_risk_reward": 1.50,
                "max_position_size": 0.20
            })

        2. Parameter langsung

            ExecutionGate(
                min_confidence=0.60,
                min_risk_reward=1.50,
                max_position_size=0.20
            )
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
        # NORMALIZE
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
    # MAIN EVALUATE
    # ==========================================================

    def evaluate(
        self,
        decision: Optional[Dict[str, Any]] = None,
        *,
        symbol: Optional[str] = None,
        action: Optional[str] = None,
        confidence: Optional[float] = None,
        position_size: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        approved: Optional[bool] = None,
        execution_allowed: Optional[bool] = None,
    ) -> ExecutionGateResult:
        """
        Evaluate execution permission.

        Mendukung dua interface.

        ----------------------------------------------------------
        FORMAT 1 — DICTIONARY
        ----------------------------------------------------------

        gate.evaluate({
            "symbol": "BTC-USD",
            "action": "BUY",
            "confidence": 0.78,
            "position_size": 0.08,
            "risk_reward_ratio": 2.4,
            "approved": True,
            "execution_allowed": True
        })

        ----------------------------------------------------------
        FORMAT 2 — KEYWORD ARGUMENTS
        ----------------------------------------------------------

        gate.evaluate(
            symbol="BTC-USD",
            action="BUY",
            confidence=0.78,
            position_size=0.08,
            risk_reward_ratio=2.4,
            approved=True,
            execution_allowed=True
        )
        """

        # ======================================================
        # NORMALIZE INPUT
        # ======================================================

        if decision is not None:

            if not isinstance(decision, dict):

                raise TypeError(
                    "decision harus berupa dictionary."
                )

            symbol = decision.get(
                "symbol",
                symbol or "UNKNOWN"
            )

            action = decision.get(
                "action",
                action or "HOLD"
            )

            confidence = decision.get(
                "confidence",
                confidence if confidence is not None else 0.0
            )

            position_size = decision.get(
                "position_size",
                position_size if position_size is not None else 0.0
            )

            risk_reward_ratio = decision.get(
                "risk_reward_ratio",
                (
                    risk_reward_ratio
                    if risk_reward_ratio is not None
                    else 0.0
                )
            )

            approved = decision.get(
                "approved",
                approved if approved is not None else False
            )

            execution_allowed = decision.get(
                "execution_allowed",
                (
                    execution_allowed
                    if execution_allowed is not None
                    else False
                )
            )

        # ======================================================
        # SAFE DEFAULTS
        # ======================================================

        symbol = str(
            symbol or "UNKNOWN"
        ).upper()

        action = str(
            action or "HOLD"
        ).upper()

        try:
            confidence = float(
                confidence if confidence is not None else 0.0
            )
        except (TypeError, ValueError):

            confidence = 0.0

        try:
            position_size = float(
                position_size
                if position_size is not None
                else 0.0
            )
        except (TypeError, ValueError):

            position_size = 0.0

        try:
            risk_reward_ratio = float(
                risk_reward_ratio
                if risk_reward_ratio is not None
                else 0.0
            )
        except (TypeError, ValueError):

            risk_reward_ratio = 0.0

        approved = bool(
            approved
            if approved is not None
            else False
        )

        execution_allowed = bool(
            execution_allowed
            if execution_allowed is not None
            else False
        )

        logger.info(
            "Execution Gate evaluating %s | action=%s",
            symbol,
            action
        )

        # ======================================================
        # HOLD
        # ======================================================

        if action == "HOLD":

            return self._blocked(
                symbol=symbol,
                action=action,
                position_size=0.0,
                confidence=confidence,
                reason="HOLD action cannot be executed.",
                checks={
                    "approved": (
                        approved
                        if self.require_approved
                        else True
                    ),

                    "execution_allowed": (
                        execution_allowed
                        if self.require_execution_allowed
                        else True
                    ),

                    "valid_action": False,

                    "confidence": (
                        confidence >= self.min_confidence
                    ),

                    "risk_reward": False,

                    "position_size": False,
                }
            )

        # ======================================================
        # VALID ACTION
        # ======================================================

        valid_action = (
            action in self.VALID_ACTIONS
        )

        if not valid_action:

            return self._blocked(
                symbol=symbol,
                action=action,
                position_size=position_size,
                confidence=confidence,
                reason=(
                    f"Invalid execution action: {action}"
                ),
                checks={
                    "approved": (
                        approved
                        if self.require_approved
                        else True
                    ),

                    "execution_allowed": (
                        execution_allowed
                        if self.require_execution_allowed
                        else True
                    ),

                    "valid_action": False,

                    "confidence": False,

                    "risk_reward": False,

                    "position_size": False,
                }
            )

        # ======================================================
        # APPROVED CHECK
        # ======================================================

        approved_check = (
            approved
            if self.require_approved
            else True
        )

        # ======================================================
        # EXECUTION PERMISSION
        # ======================================================

        execution_check = (
            execution_allowed
            if self.require_execution_allowed
            else True
        )

        # ======================================================
        # CONFIDENCE CHECK
        # ======================================================

        confidence_check = (
            confidence >= self.min_confidence
        )

        # ======================================================
        # RISK / REWARD CHECK
        # ======================================================

        risk_reward_check = (
            risk_reward_ratio >= self.min_risk_reward
        )

        # ======================================================
        # POSITION SIZE CHECK
        # ======================================================

        position_size_check = (
            position_size > 0
            and position_size <= self.max_position_size
        )

        # ======================================================
        # ALL CHECKS
        # ======================================================

        checks = {

            "approved":
                approved_check,

            "execution_allowed":
                execution_check,

            "valid_action":
                valid_action,

            "confidence":
                confidence_check,

            "risk_reward":
                risk_reward_check,

            "position_size":
                position_size_check,
        }

        # ======================================================
        # FINAL GATE
        # ======================================================

        allowed = all(
            checks.values()
        )

        if not allowed:

            failed_checks = [
                name
                for name, passed in checks.items()
                if not passed
            ]

            reason = (
                "Execution blocked. "
                "Failed checks: "
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
                checks=checks,
                metadata={
                    "risk_reward_ratio":
                        risk_reward_ratio,

                    "max_position_size":
                        self.max_position_size,

                    "min_confidence":
                        self.min_confidence,

                    "min_risk_reward":
                        self.min_risk_reward,
                }
            )

        # ======================================================
        # APPROVED
        # ======================================================

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

            timestamp=datetime.now(
                timezone.utc
            ),

            symbol=symbol,

            allowed=True,

            action=action,

            position_size=position_size,

            confidence=confidence,

            reason=reason,

            checks=checks,

            metadata={

                "risk_reward_ratio":
                    risk_reward_ratio,

                "max_position_size":
                    self.max_position_size,

                "min_confidence":
                    self.min_confidence,

                "min_risk_reward":
                    self.min_risk_reward,

                "require_approved":
                    self.require_approved,

                "require_execution_allowed":
                    self.require_execution_allowed,
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionGateResult:

        logger.warning(
            "EXECUTION BLOCKED | %s | %s | %s",
            symbol,
            action,
            reason
        )

        base_metadata = {
            "original_action": action,
            "blocked": True,
        }

        if metadata:
            base_metadata.update(
                metadata
            )

        return ExecutionGateResult(

            timestamp=datetime.now(
                timezone.utc
            ),

            symbol=symbol,

            allowed=False,

            action="HOLD",

            position_size=0.0,

            confidence=confidence,

            reason=reason,

            checks=checks,

            metadata=base_metadata,
        )


# ==============================================================
# TEST
# ==============================================================

if __name__ == "__main__":

    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s"
    )

    gate = ExecutionGate()

    # ==========================================================
    # TEST 1 — VALID BUY
    # ==========================================================

    print()
    print("=" * 70)
    print("TEST 1 — VALID BUY")
    print("=" * 70)

    buy_decision = {

        "symbol":
            "BTC-USD",

        "decision":
            "APPROVE",

        "action":
            "BUY",

        "confidence":
            0.78,

        "position_size":
            0.08,

        "risk_reward_ratio":
            2.4,

        "approved":
            True,

        "execution_allowed":
            True,
    }

    result = gate.evaluate(
        buy_decision
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=2,
            default=str
        )
    )

    # ==========================================================
    # TEST 2 — EXECUTION DISABLED
    # ==========================================================

    print()
    print("=" * 70)
    print("TEST 2 — EXECUTION DISABLED")
    print("=" * 70)

    blocked_decision = {

        "symbol":
            "BTC-USD",

        "decision":
            "APPROVE",

        "action":
            "BUY",

        "confidence":
            0.78,

        "position_size":
            0.08,

        "risk_reward_ratio":
            2.4,

        "approved":
            True,

        "execution_allowed":
            False,
    }

    result = gate.evaluate(
        blocked_decision
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=2,
            default=str
        )
    )

    # ==========================================================
    # TEST 3 — HOLD
    # ==========================================================

    print()
    print("=" * 70)
    print("TEST 3 — HOLD")
    print("=" * 70)

    hold_decision = {

        "symbol":
            "BTC-USD",

        "decision":
            "REJECT",

        "action":
            "HOLD",

        "confidence":
            0.52,

        "position_size":
            0.0,

        "risk_reward_ratio":
            0.0,

        "approved":
            False,

        "execution_allowed":
            False,
    }

    result = gate.evaluate(
        hold_decision
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=2,
            default=str
        )
    )

    # ==========================================================
    # TEST 4 — DIRECT KEYWORD INTERFACE
    # ==========================================================

    print()
    print("=" * 70)
    print("TEST 4 — KEYWORD INTERFACE")
    print("=" * 70)

    result = gate.evaluate(

        symbol="BTC-USD",

        action="SELL",

        confidence=0.81,

        position_size=0.07,

        risk_reward_ratio=2.2,

        approved=True,

        execution_allowed=True,
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=2,
            default=str
        )
    )

    # ==========================================================
    # TEST 5 — CONFIG DICTIONARY
    # ==========================================================

    print()
    print("=" * 70)
    print("TEST 5 — CONFIG DICTIONARY")
    print("=" * 70)

    config_gate = ExecutionGate({

        "min_confidence":
            0.60,

        "min_risk_reward":
            1.50,

        "max_position_size":
            0.20,

        "require_approved":
            True,

        "require_execution_allowed":
            True,
    })

    result = config_gate.evaluate(

        symbol="BTC-USD",

        action="BUY",

        confidence=0.75,

        position_size=0.10,

        risk_reward_ratio=2.0,

        approved=True,

        execution_allowed=True,
    )

    print(
        json.dumps(
            result.to_dict(),
            indent=2,
            default=str
        )
    )

    print()
    print("=" * 70)
    print("EXECUTION GATE TEST COMPLETED")
    print("=" * 70)
