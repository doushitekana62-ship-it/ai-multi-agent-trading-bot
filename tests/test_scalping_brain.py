import unittest

from app.agents.regime_engine import RegimeEngine
from app.agents.risk_engine import RiskEngine
from app.agents.signal_engine import SignalEngine


class Forecast:
    action = "buy"
    price = 100.0
    suggested_tp = 102.0
    suggested_sl = 99.0
    indicators = {"momentum_percent": 0.6}


class TestScalpingBrain(unittest.TestCase):
    def test_regime_detects_uptrend(self):
        prices = [100 + i * 0.25 for i in range(240)]
        regime = RegimeEngine().classify(prices)
        self.assertIsNotNone(regime)
        self.assertEqual(regime.name, "TREND_UP")
        self.assertGreater(regime.data_quality, 0.9)

    def test_signal_requires_quality_gates(self):
        prices = [100 + i * 0.25 for i in range(240)]
        regime = RegimeEngine().classify(prices)
        decision = SignalEngine(min_score=70).evaluate(
            Forecast(), regime, spread_percent=0.1, book_imbalance=0.8,
            btc_return_percent=0.2, liquidity_score=0.9,
            support_resistance_score=0.7, data_quality=1.0,
        )
        self.assertEqual(decision.action, "OPEN")
        self.assertGreaterEqual(decision.score, 70)
        self.assertGreater(decision.expected_edge_percent, 0)

    def test_risk_blocks_daily_loss(self):
        decision = RiskEngine().evaluate(
            daily_pnl=-30000,
            daily_start_balance=1000000,
            equity=970000,
            peak_equity=1000000,
            open_risk_percent=0.0,
            loss_streak=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("daily_loss_limit", decision.reasons)

    def test_risk_reduces_size_near_drawdown(self):
        decision = RiskEngine().evaluate(
            daily_pnl=0,
            daily_start_balance=1000000,
            equity=985000,
            peak_equity=1000000,
            open_risk_percent=0.0,
            loss_streak=0,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.risk_multiplier, 0.75)


if __name__ == "__main__":
    unittest.main()
