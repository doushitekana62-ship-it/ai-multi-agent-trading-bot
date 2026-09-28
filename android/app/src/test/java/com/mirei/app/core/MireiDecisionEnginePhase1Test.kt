package com.mirei.app.core

import com.mirei.app.execution.PaperPosition
import org.junit.Assert.assertEquals
import org.junit.Test

class MireiDecisionEnginePhase1Test {
    @Test fun stopLossOffNeverCreatesAutomaticLossSell() {
        val engine = MireiDecisionEngine(TradingConfig(manualStopLossPercent = 0.0))
        val position = PaperPosition("p", "indodax", "BTC/IDR", 10_000.0, 100.0, 0.0, 110.0, 0.0, 1L)
        val decision = engine.decidePosition(MarketSnapshot("BTC/IDR", 50.0, dataFresh = true), position, "c", 1)
        assertEquals(MireiDecisionAction.HOLD, decision.action)
    }

    @Test fun reentryRequiresFullInitialCapital() {
        val engine = MireiDecisionEngine(TradingConfig())
        val decision = engine.decideReentry(MarketSnapshot("BTC/IDR", 200.0, dataFresh = true), "c", 2, 50_000.0, 49_999.0)
        assertEquals(MireiDecisionAction.REENTRY_WAIT, decision.action)
        assertEquals("reentry_balance_insufficient_wait", decision.reason)
    }

    @Test fun reentryAtAnyPriceIsAllowedByDecisionLayer() {
        val engine = MireiDecisionEngine(TradingConfig())
        val decision = engine.decideReentry(MarketSnapshot("BTC/IDR", 200.0, dataFresh = true), "c", 2, 50_000.0, 60_000.0)
        assertEquals(MireiDecisionAction.REENTRY_BUY, decision.action)
    }
}