package com.mirei.app.storage

import com.mirei.app.execution.PaperPosition
import com.mirei.app.execution.TradeLedger

class SqliteTradeLedger(private val database: MireiDatabase) : TradeLedger {
    override fun recordOpened(position: PaperPosition) {
        database.recordTradeOpened(position)
    }

    override fun recordClosed(
        position: PaperPosition,
        exitPrice: Double,
        feeIdr: Double,
        pnlIdr: Double,
        closedAtEpochMs: Long,
        exitReason: String,
    ) {
        database.recordTradeClosed(
            positionId = position.id,
            exitPrice = exitPrice,
            feeIdr = feeIdr,
            pnlIdr = pnlIdr,
            closedAtEpochMs = closedAtEpochMs,
            exitReason = exitReason,
        )
    }
}
