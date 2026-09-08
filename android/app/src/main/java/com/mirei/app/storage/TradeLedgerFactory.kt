package com.mirei.app.storage

import android.content.Context
import com.mirei.app.execution.TradeLedger

object TradeLedgerFactory {
    fun create(context: Context): TradeLedger = SqliteTradeLedger(MireiDatabase(context.applicationContext))
}
