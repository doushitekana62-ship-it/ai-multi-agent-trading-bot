"""
Decision Engine
===============

Mengubah hasil Orchestrator + Risk Engine menjadi keputusan trading.

Prinsip:
    BUY  = bullish evidence cukup kuat
    SELL = bearish evidence cukup kuat
    HOLD = edge tidak cukup / konflik terlalu besar

Position state:
    FLAT  = tidak memiliki posisi
    LONG  = sedang memiliki posisi BUY
    SHORT = sedang memiliki posisi SELL

PENTING:
- Confidence AI bukan satu-satunya alasan untuk trading.
- Risk engine tetap menjadi gate.
- SELL tidak dipaksakan.
- BUY dan SELL menggunakan logika evaluasi yang simetris.
- Live trading tetap disabled secara default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# ============================================================
# ENUMS
# ============================================================

class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PositionState(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class DecisionStatus(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class DecisionInput:
    """
    Input yang diperlukan Decision Engine.
    """

    symbol: str

    # Orchestrator
    consensus_score: float
    confidence: float

    # Agent evidence
    sentiment_score: float
    technical_score: float
    forecast_score: float
    decision_score: float

    # Risk
    risk_score: float
    risk_reward_ratio: float
    suggested_position_size: float

    # Position
    position_state: PositionState = PositionState.FLAT

    # Optional market information
    current_price: float = 0.0


@dataclass
class DecisionResult:
    """
    Hasil akhir Decision Engine.
    """

    timestamp: str
    symbol: str

    decision: str
    action: str

    confidence: float
    position_size: float

    risk_score: float
    consensus_score: float
    risk_reward_ratio: float

    approved: bool
    execution_allowed: bool

    position_state: str
    target_position: str

    bullish_score: float
    bearish_score: float
    directional_edge: float

    reasoning: List[str]
    checks: Dict[str, bool]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# ENGINE
# ============================================================

class DecisionEngine:

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        # ----------------------------------------------------
        # Confidence
        # ----------------------------------------------------

        self.min_confidence = self.config.get(
            "min_confidence",
            0.60
        )

        # ----------------------------------------------------
        # Directional thresholds
        # ----------------------------------------------------

        self.min_directional_edge = self.config.get(
            "min_directional_edge",
            0.15
        )

        self.min_bullish_score = self.config.get(
            "min_bullish_score",
            0.45
        )

        self.min_bearish_score = self.config.get(
            "min_bearish_score",
            0.45
        )

        # ----------------------------------------------------
        # Consensus
        # ----------------------------------------------------

        self.min_consensus = self.config.get(
            "min_consensus",
            0.20
        )

        # ----------------------------------------------------
        # Risk
        # ----------------------------------------------------

        self.max_risk_score = self.config.get(
            "max_risk_score",
            0.50
        )

        self.min_risk_reward = self.config.get(
            "min_risk_reward",
            1.50
        )

        # ----------------------------------------------------
        # Position sizing
        # ----------------------------------------------------

        self.min_position_size = self.config.get(
            "min_position_size",
            0.01
        )

        self.max_position_size = self.config.get(
            "max_position_size",
            0.20
        )

        # ----------------------------------------------------
        # Execution
        # ----------------------------------------------------

        self.live_trading_enabled = self.config.get(
            "live_trading_enabled",
            False
        )

        logger.info(
            "Decision Engine initialized"
        )

    # ========================================================
    # MAIN
    # ========================================================

    def evaluate(
        self,
        data: DecisionInput
    ) -> DecisionResult:

        logger.info(
            f"Decision Engine evaluating {data.symbol}"
        )

        # ----------------------------------------------------
        # Normalize inputs
        # ----------------------------------------------------

        confidence = self._clamp(
            data.confidence,
            0.0,
            1.0
        )

        consensus = self._clamp(
            data.consensus_score,
            -1.0,
            1.0
        )

        risk_score = self._clamp(
            data.risk_score,
            0.0,
            1.0
        )

        # ----------------------------------------------------
        # Calculate directional scores
        # ----------------------------------------------------

        bullish_score = self._calculate_bullish_score(
            data
        )

        bearish_score = self._calculate_bearish_score(
            data
        )

        directional_edge = (
            bullish_score - bearish_score
        )

        # ----------------------------------------------------
        # Determine directional action
        # ----------------------------------------------------

        proposed_action = self._determine_direction(
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            directional_edge=directional_edge
        )

        # ----------------------------------------------------
        # Position-aware action
        # ----------------------------------------------------

        final_action, target_position = self._resolve_position_action(
            proposed_action,
            data.position_state
        )

        # ----------------------------------------------------
        # HOLD does not require trade approval
        # ----------------------------------------------------

        if final_action == Action.HOLD.value:

            reasoning = [
                "Directional edge is insufficient for a trade"
            ]

            if abs(directional_edge) < self.min_directional_edge:
                reasoning.append(
                    f"Directional edge {directional_edge:.4f} "
                    f"is below minimum "
                    f"{self.min_directional_edge:.4f}"
                )

            if (
                bullish_score >= self.min_bullish_score
                and bearish_score >= self.min_bearish_score
            ):
                reasoning.append(
                    "Bullish and bearish evidence are conflicting"
                )

            return self._build_result(
                data=data,
                decision=DecisionStatus.REJECT.value,
                action=Action.HOLD.value,
                confidence=confidence,
                position_size=0.0,
                approved=False,
                bullish_score=bullish_score,
                bearish_score=bearish_score,
                directional_edge=directional_edge,
                reasoning=reasoning,
                checks={
                    "confidence": confidence >= self.min_confidence,
                    "consensus": abs(consensus) >= self.min_consensus,
                    "risk": risk_score <= self.max_risk_score,
                    "risk_reward": (
                        data.risk_reward_ratio
                        >= self.min_risk_reward
                    ),
                    "position_size": True,
                    "action": False
                },
                position_state=data.position_state.value,
                target_position=target_position
            )

        # ----------------------------------------------------
        # Confidence check
        # ----------------------------------------------------

        confidence_ok = (
            confidence >= self.min_confidence
        )

        # ----------------------------------------------------
        # Directional consensus check
        # ----------------------------------------------------

        if final_action == Action.BUY.value:

            consensus_ok = (
                consensus >= self.min_consensus
            )

        elif final_action == Action.SELL.value:

            consensus_ok = (
                consensus <= -self.min_consensus
            )

        else:

            consensus_ok = False

        # ----------------------------------------------------
        # Risk checks
        # ----------------------------------------------------

        risk_ok = (
            risk_score <= self.max_risk_score
        )

        risk_reward_ok = (
            data.risk_reward_ratio
            >= self.min_risk_reward
        )

        # ----------------------------------------------------
        # Position size
        # ----------------------------------------------------

        requested_size = self._clamp(
            data.suggested_position_size,
            0.0,
            self.max_position_size
        )

        position_size_ok = (
            requested_size >= self.min_position_size
            and requested_size <= self.max_position_size
        )

        # ----------------------------------------------------
        # Action check
        # ----------------------------------------------------

        action_ok = final_action in [
            Action.BUY.value,
            Action.SELL.value
        ]

        # ----------------------------------------------------
        # Final approval
        # ----------------------------------------------------

        approved = all([
            confidence_ok,
            consensus_ok,
            risk_ok,
            risk_reward_ok,
            position_size_ok,
            action_ok
        ])

        # ----------------------------------------------------
        # Reasoning
        # ----------------------------------------------------

        reasoning = self._build_reasoning(
            action=final_action,
            confidence=confidence,
            consensus=consensus,
            risk_score=risk_score,
            risk_reward=data.risk_reward_ratio,
            position_size=requested_size,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            directional_edge=directional_edge,
            confidence_ok=confidence_ok,
            consensus_ok=consensus_ok,
            risk_ok=risk_ok,
            risk_reward_ok=risk_reward_ok,
            position_size_ok=position_size_ok,
            approved=approved
        )

        # ----------------------------------------------------
        # Execution permission
        # ----------------------------------------------------

        execution_allowed = (
            approved
            and self.live_trading_enabled
        )

        if not self.live_trading_enabled:
            reasoning.append(
                "Live execution disabled by configuration"
            )

        return self._build_result(
            data=data,
            decision=(
                DecisionStatus.APPROVE.value
                if approved
                else DecisionStatus.REJECT.value
            ),
            action=final_action,
            confidence=confidence,
            position_size=(
                requested_size
                if approved
                else 0.0
            ),
            approved=approved,
            bullish_score=bullish_score,
            bearish_score=bearish_score,
            directional_edge=directional_edge,
            reasoning=reasoning,
            checks={
                "confidence": confidence_ok,
                "consensus": consensus_ok,
                "risk": risk_ok,
                "risk_reward": risk_reward_ok,
                "position_size": position_size_ok,
                "action": action_ok
            },
            position_state=data.position_state.value,
            target_position=target_position,
            execution_allowed=execution_allowed
        )

    # ========================================================
    # BULLISH SCORE
    # ========================================================

    def _calculate_bullish_score(
        self,
        data: DecisionInput
    ) -> float:

        sentiment = max(
            0.0,
            data.sentiment_score
        )

        technical = max(
            0.0,
            data.technical_score
        )

        forecast = max(
            0.0,
            data.forecast_score
        )

        decision = max(
            0.0,
            data.decision_score
        )

        consensus = max(
            0.0,
            data.consensus_score
        )

        score = (
            sentiment * 0.20
            + technical * 0.30
            + forecast * 0.20
            + decision * 0.20
            + consensus * 0.10
        )

        return self._clamp(
            score,
            0.0,
            1.0
        )

    # ========================================================
    # BEARISH SCORE
    # ========================================================

    def _calculate_bearish_score(
        self,
        data: DecisionInput
    ) -> float:

        sentiment = max(
            0.0,
            -data.sentiment_score
        )

        technical = max(
            0.0,
            -data.technical_score
        )

        forecast = max(
            0.0,
            -data.forecast_score
        )

        decision = max(
            0.0,
            -data.decision_score
        )

        consensus = max(
            0.0,
            -data.consensus_score
        )

        score = (
            sentiment * 0.20
            + technical * 0.30
            + forecast * 0.20
            + decision * 0.20
            + consensus * 0.10
        )

        return self._clamp(
            score,
            0.0,
            1.0
        )

    # ========================================================
    # DIRECTION
    # ========================================================

    def _determine_direction(
        self,
        bullish_score: float,
        bearish_score: float,
        directional_edge: float
    ) -> str:

        # ----------------------------------------------------
        # Strong bullish
        # ----------------------------------------------------

        if (
            bullish_score >= self.min_bullish_score
            and directional_edge
            >= self.min_directional_edge
        ):
            return Action.BUY.value

        # ----------------------------------------------------
        # Strong bearish
        # ----------------------------------------------------

        if (
            bearish_score >= self.min_bearish_score
            and directional_edge
            <= -self.min_directional_edge
        ):
            return Action.SELL.value

        # ----------------------------------------------------
        # No sufficient edge
        # ----------------------------------------------------

        return Action.HOLD.value

    # ========================================================
    # POSITION RESOLUTION
    # ========================================================

    def _resolve_position_action(
        self,
        proposed_action: str,
        position_state: PositionState
    ):

        # ----------------------------------------------------
        # FLAT
        # ----------------------------------------------------

        if position_state == PositionState.FLAT:

            if proposed_action == Action.BUY.value:
                return Action.BUY.value, PositionState.LONG.value

            if proposed_action == Action.SELL.value:
                return Action.SELL.value, PositionState.SHORT.value

            return Action.HOLD.value, PositionState.FLAT.value

        # ----------------------------------------------------
        # LONG
        # ----------------------------------------------------

        if position_state == PositionState.LONG:

            if proposed_action == Action.SELL.value:
                return Action.SELL.value, PositionState.FLAT.value

            return Action.HOLD.value, PositionState.LONG.value

        # ----------------------------------------------------
        # SHORT
        # ----------------------------------------------------

        if position_state == PositionState.SHORT:

            if proposed_action == Action.BUY.value:
                return Action.BUY.value, PositionState.FLAT.value

            return Action.HOLD.value, PositionState.SHORT.value

        return Action.HOLD.value, PositionState.FLAT.value

    # ========================================================
    # REASONING
    # ========================================================

    def _build_reasoning(
        self,
        action: str,
        confidence: float,
        consensus: float,
        risk_score: float,
        risk_reward: float,
        position_size: float,
        bullish_score: float,
        bearish_score: float,
        directional_edge: float,
        confidence_ok: bool,
        consensus_ok: bool,
        risk_ok: bool,
        risk_reward_ok: bool,
        position_size_ok: bool,
        approved: bool
    ) -> List[str]:

        reasoning = []

        if action == Action.BUY.value:

            reasoning.append(
                f"Bullish score {bullish_score:.4f} "
                f"exceeds bearish score {bearish_score:.4f}"
            )

            reasoning.append(
                f"Directional edge {directional_edge:.4f} "
                f"favors BUY"
            )

        elif action == Action.SELL.value:

            reasoning.append(
                f"Bearish score {bearish_score:.4f} "
                f"exceeds bullish score {bullish_score:.4f}"
            )

            reasoning.append(
                f"Directional edge {directional_edge:.4f} "
                f"favors SELL"
            )

        # ----------------------------------------------------
        # Checks
        # ----------------------------------------------------

        if confidence_ok:

            reasoning.append(
                f"Confidence {confidence:.2%} "
                f">= minimum {self.min_confidence:.2%}"
            )

        else:

            reasoning.append(
                f"Confidence {confidence:.2%} "
                f"is below minimum {self.min_confidence:.2%}"
            )

        if consensus_ok:

            reasoning.append(
                f"Consensus {consensus:.4f} "
                f"supports {action}"
            )

        else:

            reasoning.append(
                f"Consensus {consensus:.4f} "
                f"does not sufficiently support {action}"
            )

        if risk_ok:

            reasoning.append(
                f"Risk score {risk_score:.4f} "
                f"is within allowed limit"
            )

        else:

            reasoning.append(
                f"Risk score {risk_score:.4f} "
                f"exceeds allowed limit"
            )

        if risk_reward_ok:

            reasoning.append(
                f"Risk/reward {risk_reward:.2f} "
                f"passes minimum {self.min_risk_reward:.2f}"
            )

        else:

            reasoning.append(
                f"Risk/reward {risk_reward:.2f} "
                f"fails minimum {self.min_risk_reward:.2f}"
            )

        if position_size_ok:

            reasoning.append(
                f"Position size {position_size:.2%} "
                f"is within allowed range"
            )

        else:

            reasoning.append(
                "Position size is outside allowed range"
            )

        if approved:

            reasoning.append(
                "Decision passed all decision-engine checks"
            )

        else:

            reasoning.append(
                "Decision rejected by decision-engine checks"
            )

        return reasoning

    # ========================================================
    # RESULT BUILDER
    # ========================================================

    def _build_result(
        self,
        data: DecisionInput,
        decision: str,
        action: str,
        confidence: float,
        position_size: float,
        approved: bool,
        bullish_score: float,
        bearish_score: float,
        directional_edge: float,
        reasoning: List[str],
        checks: Dict[str, bool],
        position_state: str,
        target_position: str,
        execution_allowed: bool = False
    ) -> DecisionResult:

        return DecisionResult(
            timestamp=datetime.now().isoformat(),
            symbol=data.symbol,

            decision=decision,
            action=action,

            confidence=confidence,
            position_size=position_size,

            risk_score=data.risk_score,
            consensus_score=data.consensus_score,
            risk_reward_ratio=data.risk_reward_ratio,

            approved=approved,
            execution_allowed=execution_allowed,

            position_state=position_state,
            target_position=target_position,

            bullish_score=bullish_score,
            bearish_score=bearish_score,
            directional_edge=directional_edge,

            reasoning=reasoning,
            checks=checks,

            metadata={
                "requested_action": action,
                "requested_position_size": data.suggested_position_size,
                "current_price": data.current_price,
                "live_trading_enabled": self.live_trading_enabled
            }
        )

    # ========================================================
    # UTILITY
    # ========================================================

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float
    ) -> float:

        return max(
            minimum,
            min(
                maximum,
                float(value)
            )
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    import json

    logging.basicConfig(
        level=logging.INFO
    )

    engine = DecisionEngine({
        "min_confidence": 0.60,
        "min_consensus": 0.20,
        "min_directional_edge": 0.15,
        "min_bullish_score": 0.45,
        "min_bearish_score": 0.45,
        "max_risk_score": 0.50,
        "min_risk_reward": 1.50,
        "min_position_size": 0.01,
        "max_position_size": 0.20,
        "live_trading_enabled": False
    })

    # ========================================================
    # TEST 1 — BUY
    # ========================================================

    buy_input = DecisionInput(
        symbol="BTC-USD",

        consensus_score=0.42,
        confidence=0.78,

        sentiment_score=0.65,
        technical_score=0.72,
        forecast_score=0.68,
        decision_score=0.70,

        risk_score=0.25,
        risk_reward_ratio=2.40,
        suggested_position_size=0.08,

        position_state=PositionState.FLAT,

        current_price=62760.21
    )

    buy_result = engine.evaluate(
        buy_input
    )

    print("\n")
    print("=" * 70)
    print("TEST 1 — BULLISH")
    print("=" * 70)

    print(
        json.dumps(
            buy_result.to_dict(),
            indent=2
        )
    )

    # ========================================================
    # TEST 2 — SELL
    # ========================================================

    sell_input = DecisionInput(
        symbol="BTC-USD",

        consensus_score=-0.46,
        confidence=0.81,

        sentiment_score=-0.65,
        technical_score=-0.74,
        forecast_score=-0.69,
        decision_score=-0.71,

        risk_score=0.22,
        risk_reward_ratio=2.20,
        suggested_position_size=0.07,

        position_state=PositionState.FLAT,

        current_price=62760.21
    )

    sell_result = engine.evaluate(
        sell_input
    )

    print("\n")
    print("=" * 70)
    print("TEST 2 — BEARISH")
    print("=" * 70)

    print(
        json.dumps(
            sell_result.to_dict(),
            indent=2
        )
    )

    # ========================================================
    # TEST 3 — CONFLICT → HOLD
    # ========================================================

    hold_input = DecisionInput(
        symbol="BTC-USD",

        consensus_score=0.03,
        confidence=0.64,

        sentiment_score=0.40,
        technical_score=-0.42,
        forecast_score=0.15,
        decision_score=-0.10,

        risk_score=0.35,
        risk_reward_ratio=1.20,
        suggested_position_size=0.08,

        position_state=PositionState.FLAT,

        current_price=62760.21
    )

    hold_result = engine.evaluate(
        hold_input
    )

    print("\n")
    print("=" * 70)
    print("TEST 3 — CONFLICT")
    print("=" * 70)

    print(
        json.dumps(
            hold_result.to_dict(),
            indent=2
        )
    )
