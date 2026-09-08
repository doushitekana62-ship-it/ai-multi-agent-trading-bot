package com.mirei.app.storage

import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger

class SqliteTradeLedger(private val database: MireiDatabase) : TradeLedger {
    override fun recordOpened(position: PaperPosition, entryFeeIdr: Double) {
        database.recordTradeOpened(position, entryFeeIdr)
    }

    override fun recordClosed(
        position: PaperPosition,
        exitPrice: Double,
        feeIdr: Double,
        pnlIdr: Double,
        closedAtEpochMs: Long,
        exitReason: String,
    ) {
        database.recordTradeClosed(position.id, exitPrice, feeIdr, pnlIdr, closedAtEpochMs, exitReason)
    }
}
