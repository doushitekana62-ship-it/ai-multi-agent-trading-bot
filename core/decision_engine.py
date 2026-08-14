"""
Decision Engine
===============

Lapisan pengambilan keputusan akhir sebelum Executor.

Alur:

AI Agents
    ↓
Orchestrator
    ↓
Risk Engine
    ↓
Decision Engine
    ↓
Executor

Decision Engine TIDAK melakukan order.

Tugasnya:
1. Membaca keputusan Orchestrator
2. Membaca hasil Risk Engine
3. Mengevaluasi confidence
4. Mengevaluasi consensus
5. Mengevaluasi risk/reward
6. Mengevaluasi exposure
7. Menentukan apakah keputusan boleh dieksekusi
8. Menghasilkan reasoning yang dapat diaudit

Default:
- SAFE
- PAPER TRADING
- Tidak pernah memaksa BUY/SELL
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class DecisionResult:
    timestamp: datetime

    symbol: str

    decision: str
    action: str

    confidence: float

    position_size: float

    risk_score: float

    consensus_score: float

    risk_reward_ratio: Optional[float]

    approved: bool

    execution_allowed: bool

    reasoning: list

    checks: Dict[str, bool]

    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)

        data["timestamp"] = self.timestamp.isoformat()

        return data


# ============================================================
# DECISION ENGINE
# ============================================================

class DecisionEngine:

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        # ----------------------------------------------------
        # THRESHOLDS
        # ----------------------------------------------------

        self.min_confidence = self.config.get(
            "min_confidence",
            0.60
        )

        self.min_consensus = self.config.get(
            "min_consensus",
            0.10
        )

        self.max_risk_score = self.config.get(
            "max_risk_score",
            0.70
        )

        self.min_risk_reward = self.config.get(
            "min_risk_reward",
            1.5
        )

        self.max_position_size = self.config.get(
            "max_position_size",
            0.20
        )

        # ----------------------------------------------------
        # SAFETY
        # ----------------------------------------------------

        self.allow_live_trading = self.config.get(
            "allow_live_trading",
            False
        )

        logger.info(
            "Decision Engine initialized"
        )

        logger.info(
            "Configuration: "
            f"min_confidence={self.min_confidence}, "
            f"min_consensus={self.min_consensus}, "
            f"max_risk_score={self.max_risk_score}, "
            f"min_rr={self.min_risk_reward}"
        )

    # ========================================================
    # MAIN DECISION METHOD
    # ========================================================

    def evaluate(
        self,
        orchestrator_result: Any,
        risk_result: Any
    ) -> DecisionResult:

        """
        Evaluate apakah keputusan Orchestrator boleh dieksekusi.

        Parameters
        ----------
        orchestrator_result:
            Hasil dari Orchestrator.

        risk_result:
            Hasil dari Risk Engine.

        Returns
        -------
        DecisionResult
        """

        try:

            # ------------------------------------------------
            # Extract orchestrator data
            # ------------------------------------------------

            symbol = self._get_value(
                orchestrator_result,
                "symbol",
                "UNKNOWN"
            )

            action = self._get_value(
                orchestrator_result,
                "final_action",
                "HOLD"
            )

            confidence = float(
                self._get_value(
                    orchestrator_result,
                    "final_confidence",
                    0.0
                )
            )

            position_size = float(
                self._get_value(
                    orchestrator_result,
                    "position_size",
                    0.0
                )
            )

            consensus_score = float(
                self._get_value(
                    orchestrator_result,
                    "consensus_score",
                    0.0
                )
            )

            # ------------------------------------------------
            # Extract risk data
            # ------------------------------------------------

            risk_score = float(
                self._get_value(
                    risk_result,
                    "risk_score",
                    1.0
                )
            )

            risk_reward_ratio = self._get_value(
                risk_result,
                "risk_reward_ratio",
                None
            )

            if risk_reward_ratio is not None:

                try:
                    risk_reward_ratio = float(
                        risk_reward_ratio
                    )

                except (ValueError, TypeError):

                    risk_reward_ratio = None

            # ------------------------------------------------
            # Normalize action
            # ------------------------------------------------

            action = str(action).upper()

            # ------------------------------------------------
            # HOLD is always safe
            # ------------------------------------------------

            if action == "HOLD":

                return self._build_hold_result(
                    symbol=symbol,
                    confidence=confidence,
                    position_size=position_size,
                    consensus_score=consensus_score,
                    risk_score=risk_score,
                    risk_reward_ratio=risk_reward_ratio
                )

            # ------------------------------------------------
            # Individual checks
            # ------------------------------------------------

            checks = {}

            reasoning = []

            # =================================================
            # CHECK 1 — CONFIDENCE
            # =================================================

            confidence_ok = (
                confidence >= self.min_confidence
            )

            checks["confidence"] = confidence_ok

            if confidence_ok:

                reasoning.append(
                    f"Confidence {confidence:.2%} "
                    f">= minimum {self.min_confidence:.2%}"
                )

            else:

                reasoning.append(
                    f"Confidence {confidence:.2%} "
                    f"below minimum {self.min_confidence:.2%}"
                )

            # =================================================
            # CHECK 2 — CONSENSUS
            # =================================================

            consensus_ok = (
                abs(consensus_score)
                >= self.min_consensus
            )

            checks["consensus"] = consensus_ok

            if consensus_ok:

                reasoning.append(
                    f"Consensus score "
                    f"{consensus_score:.4f} "
                    f"passes threshold"
                )

            else:

                reasoning.append(
                    f"Consensus score "
                    f"{consensus_score:.4f} "
                    f"is too weak"
                )

            # =================================================
            # CHECK 3 — RISK SCORE
            # =================================================

            risk_ok = (
                risk_score <= self.max_risk_score
            )

            checks["risk"] = risk_ok

            if risk_ok:

                reasoning.append(
                    f"Risk score "
                    f"{risk_score:.4f} "
                    f"is within allowed limit"
                )

            else:

                reasoning.append(
                    f"Risk score "
                    f"{risk_score:.4f} "
                    f"exceeds maximum "
                    f"{self.max_risk_score:.4f}"
                )

            # =================================================
            # CHECK 4 — RISK / REWARD
            # =================================================

            if risk_reward_ratio is None:

                rr_ok = False

                reasoning.append(
                    "Risk/reward ratio unavailable"
                )

            else:

                rr_ok = (
                    risk_reward_ratio
                    >= self.min_risk_reward
                )

                if rr_ok:

                    reasoning.append(
                        f"Risk/reward "
                        f"{risk_reward_ratio:.2f} "
                        f"passes minimum "
                        f"{self.min_risk_reward:.2f}"
                    )

                else:

                    reasoning.append(
                        f"Risk/reward "
                        f"{risk_reward_ratio:.2f} "
                        f"is below minimum "
                        f"{self.min_risk_reward:.2f}"
                    )

            checks["risk_reward"] = rr_ok

            # =================================================
            # CHECK 5 — POSITION SIZE
            # =================================================

            position_ok = (
                0.0 < position_size
                <= self.max_position_size
            )

            checks["position_size"] = position_ok

            if position_ok:

                reasoning.append(
                    f"Position size "
                    f"{position_size:.2%} "
                    f"is within allowed range"
                )

            else:

                reasoning.append(
                    f"Position size "
                    f"{position_size:.2%} "
                    f"is invalid or exceeds "
                    f"maximum "
                    f"{self.max_position_size:.2%}"
                )

            # =================================================
            # CHECK 6 — ACTION
            # =================================================

            valid_actions = {
                "BUY",
                "STRONG_BUY",
                "SELL",
                "STRONG_SELL"
            }

            action_ok = action in valid_actions

            checks["action"] = action_ok

            if not action_ok:

                reasoning.append(
                    f"Invalid action: {action}"
                )

            # =================================================
            # FINAL APPROVAL
            # =================================================

            approved = all(checks.values())

            # ------------------------------------------------
            # Execution safety
            # ------------------------------------------------

            execution_allowed = (
                approved
                and self.allow_live_trading
            )

            # ------------------------------------------------
            # IMPORTANT:
            #
            # approved != execution_allowed
            #
            # approved means:
            # "decision mathematically passes"
            #
            # execution_allowed means:
            # "system is permitted to execute"
            #
            # Default live trading = FALSE
            # ------------------------------------------------

            if approved:

                reasoning.append(
                    "Decision passed all "
                    "decision-engine checks"
                )

            else:

                reasoning.append(
                    "Decision BLOCKED because "
                    "one or more checks failed"
                )

            if not self.allow_live_trading:

                reasoning.append(
                    "Live execution disabled by configuration"
                )

            decision = (
                "APPROVE"
                if approved
                else "REJECT"
            )

            # ------------------------------------------------
            # Safety override
            # ------------------------------------------------

            if not approved:

                final_action = "HOLD"
                final_position_size = 0.0

            else:

                final_action = action
                final_position_size = min(
                    position_size,
                    self.max_position_size
                )

            return DecisionResult(

                timestamp=datetime.now(),

                symbol=symbol,

                decision=decision,

                action=final_action,

                confidence=confidence,

                position_size=final_position_size,

                risk_score=risk_score,

                consensus_score=consensus_score,

                risk_reward_ratio=risk_reward_ratio,

                approved=approved,

                execution_allowed=execution_allowed,

                reasoning=reasoning,

                checks=checks,

                metadata={
                    "requested_action": action,
                    "requested_position_size": position_size,
                    "live_trading_enabled":
                        self.allow_live_trading
                }
            )

        except Exception as e:

            logger.exception(
                "Decision Engine error"
            )

            return self._fail_safe_result(
                symbol=self._get_value(
                    orchestrator_result,
                    "symbol",
                    "UNKNOWN"
                ),
                error=str(e)
            )

    # ========================================================
    # HOLD RESULT
    # ========================================================

    def _build_hold_result(
        self,
        symbol: str,
        confidence: float,
        position_size: float,
        consensus_score: float,
        risk_score: float,
        risk_reward_ratio: Optional[float]
    ) -> DecisionResult:

        return DecisionResult(

            timestamp=datetime.now(),

            symbol=symbol,

            decision="HOLD",

            action="HOLD",

            confidence=confidence,

            position_size=0.0,

            risk_score=risk_score,

            consensus_score=consensus_score,

            risk_reward_ratio=risk_reward_ratio,

            approved=True,

            execution_allowed=False,

            reasoning=[
                "Orchestrator action is HOLD",
                "No order should be created",
                "Decision Engine confirms HOLD"
            ],

            checks={
                "confidence": True,
                "consensus": True,
                "risk": True,
                "risk_reward": True,
                "position_size": True,
                "action": True
            },

            metadata={
                "requested_action": "HOLD",
                "requested_position_size": position_size,
                "live_trading_enabled":
                    self.allow_live_trading
            }
        )

    # ========================================================
    # FAIL SAFE
    # ========================================================

    def _fail_safe_result(
        self,
        symbol: str,
        error: str
    ) -> DecisionResult:

        return DecisionResult(

            timestamp=datetime.now(),

            symbol=symbol,

            decision="ERROR",

            action="HOLD",

            confidence=0.0,

            position_size=0.0,

            risk_score=1.0,

            consensus_score=0.0,

            risk_reward_ratio=None,

            approved=False,

            execution_allowed=False,

            reasoning=[
                "Decision Engine encountered an error",
                "System switched to HOLD",
                f"Error: {error}"
            ],

            checks={
                "confidence": False,
                "consensus": False,
                "risk": False,
                "risk_reward": False,
                "position_size": False,
                "action": False
            },

            metadata={
                "error": error
            }
        )

    # ========================================================
    # VALUE HELPER
    # ========================================================

    @staticmethod
    def _get_value(
        obj: Any,
        key: str,
        default: Any = None
    ) -> Any:

        if obj is None:
            return default

        # Dictionary
        if isinstance(obj, dict):

            return obj.get(key, default)

        # Dataclass / object
        return getattr(
            obj,
            key,
            default
        )


# ============================================================
# FACTORY
# ============================================================

def create_decision_engine(
    config: Optional[Dict[str, Any]] = None
) -> DecisionEngine:

    return DecisionEngine(config)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    # --------------------------------------------------------
    # Fake orchestrator result
    # --------------------------------------------------------

    orchestrator = {

        "symbol": "BTC-USD",

        "final_action": "BUY",

        "final_confidence": 0.78,

        "position_size": 0.08,

        "consensus_score": 0.42
    }

    # --------------------------------------------------------
    # Fake risk engine result
    # --------------------------------------------------------

    risk = {

        "risk_score": 0.25,

        "risk_reward_ratio": 2.4
    }

    # --------------------------------------------------------
    # Engine
    # --------------------------------------------------------

    engine = DecisionEngine({

        "min_confidence": 0.60,

        "min_consensus": 0.10,

        "max_risk_score": 0.70,

        "min_risk_reward": 1.5,

        "max_position_size": 0.20,

        # IMPORTANT:
        # Keep FALSE while testing.
        "allow_live_trading": False
    })

    result = engine.evaluate(
        orchestrator,
        risk
    )

    print("\n")
    print("=" * 60)
    print("DECISION ENGINE RESULT")
    print("=" * 60)

    print(
        json.dumps(
            result.to_dict(),
            indent=2
        )
    )
