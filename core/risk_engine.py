"""
Risk Engine
===========

Risk Engine bertugas menjadi lapisan pengaman antara
Orchestrator dan Executor.

Prinsip utama:

    AI DECISION != TRADE PERMISSION

Orchestrator menghasilkan keputusan berdasarkan agent.

Risk Engine mengevaluasi apakah keputusan tersebut
secara matematis layak untuk dieksekusi.

Risk Engine TIDAK membuat prediksi pasar.

Risk Engine mengontrol:
- confidence
- position sizing
- maximum exposure
- stop loss
- take profit
- risk/reward ratio
- daily loss
- jumlah posisi aktif
- cooldown
- market volatility
"""

import logging
import math
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any


logger = logging.getLogger(__name__)


# ============================================================
# RISK DECISION
# ============================================================

@dataclass
class RiskDecision:
    """
    Hasil evaluasi Risk Engine.
    """

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
        """
        Convert result menjadi dictionary.
        """
        data = asdict(self)

        data["timestamp"] = self.timestamp.isoformat()

        return data


# ============================================================
# RISK ENGINE
# ============================================================

class RiskEngine:
    """
    Mathematical risk management layer.

    Risk Engine tidak memutuskan arah market.

    Ia hanya menjawab:

        "Apakah keputusan AI aman untuk dieksekusi?"
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):

        self.config = config or {}

        # ----------------------------------------------------
        # CAPITAL
        # ----------------------------------------------------

        self.initial_capital = float(
            self.config.get(
                "initial_capital",
                10000.0
            )
        )

        self.current_capital = float(
            self.config.get(
                "current_capital",
                self.initial_capital
            )
        )

        # ----------------------------------------------------
        # POSITION LIMITS
        # ----------------------------------------------------

        self.max_position_size = float(
            self.config.get(
                "max_position_size",
                0.20
            )
        )

        self.max_total_exposure = float(
            self.config.get(
                "max_total_exposure",
                0.50
            )
        )

        self.max_open_positions = int(
            self.config.get(
                "max_open_positions",
                5
            )
        )

        # ----------------------------------------------------
        # CONFIDENCE
        # ----------------------------------------------------

        self.minimum_confidence = float(
            self.config.get(
                "minimum_confidence",
                0.55
            )
        )

        self.high_confidence = float(
            self.config.get(
                "high_confidence",
                0.75
            )
        )

        # ----------------------------------------------------
        # RISK PER TRADE
        # ----------------------------------------------------

        self.max_risk_per_trade = float(
            self.config.get(
                "max_risk_per_trade",
                0.01
            )
        )

        # ----------------------------------------------------
        # DAILY LOSS
        # ----------------------------------------------------

        self.max_daily_loss = float(
            self.config.get(
                "max_daily_loss",
                0.03
            )
        )

        # ----------------------------------------------------
        # RISK / REWARD
        # ----------------------------------------------------

        self.minimum_risk_reward = float(
            self.config.get(
                "minimum_risk_reward",
                1.5
            )
        )

        # ----------------------------------------------------
        # VOLATILITY
        # ----------------------------------------------------

        self.max_volatility = float(
            self.config.get(
                "max_volatility",
                0.08
            )
        )

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.daily_pnl = 0.0

        self.open_positions = 0

        self.current_exposure = 0.0

        self.last_decision_time: Optional[datetime] = None

        self.total_evaluations = 0

        self.approved_trades = 0

        self.rejected_trades = 0

        logger.info(
            "RiskEngine initialized"
        )

    # ========================================================
    # MAIN EVALUATION
    # ========================================================

    def evaluate(
        self,
        symbol: str,
        action: str,
        confidence: float,
        position_size: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        volatility: Optional[float] = None,
        current_exposure: Optional[float] = None,
        open_positions: Optional[int] = None,
        daily_pnl: Optional[float] = None
    ) -> RiskDecision:

        self.total_evaluations += 1

        # ----------------------------------------------------
        # Normalize input
        # ----------------------------------------------------

        action = str(action).upper()

        confidence = self._clamp(
            confidence,
            0.0,
            1.0
        )

        position_size = self._clamp(
            position_size,
            0.0,
            self.max_position_size
        )

        entry_price = float(entry_price or 0.0)

        volatility = (
            float(volatility)
            if volatility is not None
            else 0.0
        )

        exposure = (
            float(current_exposure)
            if current_exposure is not None
            else self.current_exposure
        )

        positions = (
            int(open_positions)
            if open_positions is not None
            else self.open_positions
        )

        daily_loss = (
            float(daily_pnl)
            if daily_pnl is not None
            else self.daily_pnl
        )

        # ----------------------------------------------------
        # HOLD
        # ----------------------------------------------------

        if action == "HOLD":

            return self._reject(
                symbol=symbol,
                action=action,
                confidence=confidence,
                position_size=0.0,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="AI decision is HOLD"
            )

        # ----------------------------------------------------
        # Invalid price
        # ----------------------------------------------------

        if entry_price <= 0:

            return self._reject(
                symbol,
                action,
                confidence,
                position_size,
                entry_price,
                stop_loss,
                take_profit,
                "Invalid entry price"
            )

        # ----------------------------------------------------
        # Confidence check
        # ----------------------------------------------------

        if confidence < self.minimum_confidence:

            return self._reject(
                symbol,
                action,
                confidence,
                position_size,
                entry_price,
                stop_loss,
                take_profit,
                (
                    f"Confidence {confidence:.2%} "
                    f"is below minimum "
                    f"{self.minimum_confidence:.2%}"
                )
            )

        # ----------------------------------------------------
        # Daily loss protection
        # ----------------------------------------------------

        if daily_loss <= -self.max_daily_loss:

            return self._reject(
                symbol,
                action,
                confidence,
                position_size,
                entry_price,
                stop_loss,
                take_profit,
                (
                    f"Daily loss limit reached: "
                    f"{daily_loss:.2%}"
                )
            )

        # ----------------------------------------------------
        # Maximum positions
        # ----------------------------------------------------

        if positions >= self.max_open_positions:

            return self._reject(
                symbol,
                action,
                confidence,
                position_size,
                entry_price,
                stop_loss,
                take_profit,
                (
                    f"Maximum open positions reached: "
                    f"{positions}/{self.max_open_positions}"
                )
            )

        # ----------------------------------------------------
        # Exposure protection
        # ----------------------------------------------------

        requested_exposure = exposure + position_size

        if requested_exposure > self.max_total_exposure:

            remaining_exposure = max(
                0.0,
                self.max_total_exposure - exposure
            )

            if remaining_exposure <= 0:

                return self._reject(
                    symbol,
                    action,
                    confidence,
                    position_size,
                    entry_price,
                    stop_loss,
                    take_profit,
                    "Maximum portfolio exposure reached"
                )

            position_size = min(
                position_size,
                remaining_exposure
            )

        # ----------------------------------------------------
        # Volatility protection
        # ----------------------------------------------------

        if volatility > self.max_volatility:

            # Jangan langsung reject.
            #
            # Kita turunkan position size.
            #
            # Ini penting karena Risk Engine seharusnya
            # mampu beradaptasi terhadap kondisi market.

            volatility_factor = (
                self.max_volatility /
                volatility
            )

            position_size *= self._clamp(
                volatility_factor,
                0.25,
                1.0
            )

        # ----------------------------------------------------
        # Confidence based sizing
        # ----------------------------------------------------

        confidence_factor = self._confidence_factor(
            confidence
        )

        adjusted_position_size = (
            position_size *
            confidence_factor
        )

        # ----------------------------------------------------
        # Hard cap
        # ----------------------------------------------------

        adjusted_position_size = min(
            adjusted_position_size,
            self.max_position_size
        )

        # ----------------------------------------------------
        # Minimum meaningful position
        # ----------------------------------------------------

        if adjusted_position_size <= 0.001:

            return self._reject(
                symbol,
                action,
                confidence,
                position_size,
                entry_price,
                stop_loss,
                take_profit,
                "Calculated position size is too small"
            )

        # ----------------------------------------------------
        # Calculate RISK / REWARD
        # ----------------------------------------------------

        risk_amount, reward_amount, rr = (
            self._calculate_risk_reward(
                action=action,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
        )

        # ----------------------------------------------------
        # Risk / Reward validation
        # ----------------------------------------------------

        if (
            stop_loss is not None
            and take_profit is not None
            and rr < self.minimum_risk_reward
        ):

            return self._reject(
                symbol,
                action,
                confidence,
                adjusted_position_size,
                entry_price,
                stop_loss,
                take_profit,
                (
                    f"Risk/Reward {rr:.2f} "
                    f"is below minimum "
                    f"{self.minimum_risk_reward:.2f}"
                )
            )

        # ----------------------------------------------------
        # Risk score
        # ----------------------------------------------------

        risk_score = self._calculate_risk_score(
            confidence=confidence,
            volatility=volatility,
            risk_reward=rr
        )

        # ----------------------------------------------------
        # Final approval
        # ----------------------------------------------------

        self.approved_trades += 1

        self.last_decision_time = datetime.now()

        logger.info(
            f"RISK APPROVED | "
            f"{symbol} | "
            f"{action} | "
            f"confidence={confidence:.2%} | "
            f"position={adjusted_position_size:.2%} | "
            f"RR={rr:.2f}"
        )

        return RiskDecision(
            approved=True,

            symbol=symbol,
            action=action,

            original_confidence=confidence,
            adjusted_confidence=confidence_factor * confidence,

            requested_position_size=position_size,
            approved_position_size=adjusted_position_size,

            entry_price=entry_price,

            stop_loss=stop_loss,
            take_profit=take_profit,

            risk_amount=risk_amount,
            reward_amount=reward_amount,
            risk_reward_ratio=rr,

            exposure=exposure + adjusted_position_size,

            reason="Risk checks passed",

            risk_score=risk_score,

            timestamp=datetime.now()
        )

    # ========================================================
    # CONFIDENCE FACTOR
    # ========================================================

    def _confidence_factor(
        self,
        confidence: float
    ) -> float:

        if confidence < self.minimum_confidence:

            return 0.0

        if confidence >= self.high_confidence:

            return 1.0

        # Linear interpolation.
        #
        # Example:
        #
        # 55% confidence -> 0.0
        # 65% confidence -> 0.5
        # 75% confidence -> 1.0

        denominator = (
            self.high_confidence -
            self.minimum_confidence
        )

        if denominator <= 0:
            return 1.0

        return (
            confidence -
            self.minimum_confidence
        ) / denominator

    # ========================================================
    # RISK / REWARD
    # ========================================================

    def _calculate_risk_reward(
        self,
        action: str,
        entry_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float]
    ):

        if (
            stop_loss is None
            or take_profit is None
        ):

            return 0.0, 0.0, 0.0

        if action in [
            "BUY",
            "STRONG_BUY"
        ]:

            risk = max(
                0.0,
                entry_price - stop_loss
            )

            reward = max(
                0.0,
                take_profit - entry_price
            )

        else:

            risk = max(
                0.0,
                stop_loss - entry_price
            )

            reward = max(
                0.0,
                entry_price - take_profit
            )

        if risk <= 0:

            return risk, reward, 0.0

        rr = reward / risk

        return risk, reward, rr

    # ========================================================
    # RISK SCORE
    # ========================================================

    def _calculate_risk_score(
        self,
        confidence: float,
        volatility: float,
        risk_reward: float
    ) -> float:

        # Confidence contribution
        confidence_score = confidence

        # Volatility contribution
        volatility_score = max(
            0.0,
            1.0 - (
                volatility /
                self.max_volatility
            )
        ) if self.max_volatility > 0 else 0.0

        # R/R contribution
        if risk_reward <= 0:

            rr_score = 0.5

        else:

            rr_score = min(
                1.0,
                risk_reward /
                max(
                    self.minimum_risk_reward,
                    1.0
                )
            )

        # Weighted mathematical score
        score = (
            confidence_score * 0.45
            +
            volatility_score * 0.25
            +
            rr_score * 0.30
        )

        return self._clamp(
            score,
            0.0,
            1.0
        )

    # ========================================================
    # REJECT
    # ========================================================

    def _reject(
        self,
        symbol: str,
        action: str,
        confidence: float,
        position_size: float,
        entry_price: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        reason: str
    ) -> RiskDecision:

        self.rejected_trades += 1

        logger.warning(
            f"RISK REJECTED | "
            f"{symbol} | "
            f"{action} | "
            f"{reason}"
        )

        return RiskDecision(
            approved=False,

            symbol=symbol,
            action=action,

            original_confidence=confidence,
            adjusted_confidence=0.0,

            requested_position_size=position_size,
            approved_position_size=0.0,

            entry_price=entry_price,

            stop_loss=stop_loss,
            take_profit=take_profit,

            risk_amount=0.0,
            reward_amount=0.0,
            risk_reward_ratio=0.0,

            exposure=self.current_exposure,

            reason=reason,

            risk_score=0.0,

            timestamp=datetime.now()
        )

    # ========================================================
    # STATE MANAGEMENT
    # ========================================================

    def update_portfolio(
        self,
        capital: Optional[float] = None,
        daily_pnl: Optional[float] = None,
        exposure: Optional[float] = None,
        open_positions: Optional[int] = None
    ):

        if capital is not None:

            self.current_capital = float(
                capital
            )

        if daily_pnl is not None:

            self.daily_pnl = float(
                daily_pnl
            )

        if exposure is not None:

            self.current_exposure = float(
                exposure
            )

        if open_positions is not None:

            self.open_positions = int(
                open_positions
            )

    # ========================================================
    # STATISTICS
    # ========================================================

    def get_summary(self) -> Dict[str, Any]:

        approval_rate = 0.0

        if self.total_evaluations > 0:

            approval_rate = (
                self.approved_trades /
                self.total_evaluations
            )

        return {

            "initial_capital":
                self.initial_capital,

            "current_capital":
                self.current_capital,

            "daily_pnl":
                self.daily_pnl,

            "daily_loss_limit":
                self.max_daily_loss,

            "open_positions":
                self.open_positions,

            "max_open_positions":
                self.max_open_positions,

            "current_exposure":
                self.current_exposure,

            "max_total_exposure":
                self.max_total_exposure,

            "total_evaluations":
                self.total_evaluations,

            "approved_trades":
                self.approved_trades,

            "rejected_trades":
                self.rejected_trades,

            "approval_rate":
                approval_rate
        }

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
                value
            )
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO
    )

    engine = RiskEngine({

        "initial_capital": 10000,

        "minimum_confidence": 0.55,

        "high_confidence": 0.75,

        "max_position_size": 0.20,

        "max_total_exposure": 0.50,

        "max_open_positions": 5,

        "max_risk_per_trade": 0.01,

        "max_daily_loss": 0.03,

        "minimum_risk_reward": 1.5,

        "max_volatility": 0.08
    })

    result = engine.evaluate(

        symbol="BTC-USD",

        action="BUY",

        confidence=0.72,

        position_size=0.15,

        entry_price=62760,

        stop_loss=62000,

        take_profit=64500,

        volatility=0.03,

        current_exposure=0.10,

        open_positions=1,

        daily_pnl=0.0
    )

    print("\n==============================")
    print("RISK ENGINE RESULT")
    print("==============================")

    import json

    print(
        json.dumps(
            result.to_dict(),
            indent=2
        )
    )

    print("\n==============================")
    print("RISK ENGINE SUMMARY")
    print("==============================")

    print(
        json.dumps(
            engine.get_summary(),
            indent=2
        )
    )
