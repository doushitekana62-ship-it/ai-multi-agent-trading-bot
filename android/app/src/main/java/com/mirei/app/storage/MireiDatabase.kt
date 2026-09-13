package com.mirei.app.storage

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.mirei.app.execution.PaperPosition

class MireiDatabase(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""CREATE TABLE trades (id TEXT PRIMARY KEY, exchange_id TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, status TEXT NOT NULL, entry_price REAL, exit_price REAL, stake_idr REAL NOT NULL, fee_idr REAL NOT NULL DEFAULT 0, pnl_idr REAL NOT NULL DEFAULT 0, opened_at INTEGER NOT NULL, closed_at INTEGER, exit_reason TEXT, entry_reason TEXT NOT NULL DEFAULT 'entry_filled')""")
        db.execSQL("""CREATE TABLE suggestions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL, confidence REAL NOT NULL, reason TEXT NOT NULL, outcome TEXT)""")
        db.execSQL("""CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, event_type TEXT NOT NULL, details TEXT NOT NULL)""")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) db.execSQL("ALTER TABLE trades ADD COLUMN exit_reason TEXT")
        if (oldVersion < 3) db.execSQL("ALTER TABLE trades ADD COLUMN entry_reason TEXT NOT NULL DEFAULT 'entry_filled'")
    }

    fun recordTradeOpened(position: PaperPosition, entryFeeIdr: Double) {
        require(entryFeeIdr >= 0.0)
        writableDatabase.insertOrThrow("trades", null, ContentValues().apply {
            put("id", position.id)
            put("exchange_id", position.exchangeId)
            put("symbol", position.symbol)
            put("side", when (position.entryReason) { "initial_holding" -> "INITIAL_HOLDING"; "re_entry", "sl_re_entry" -> "RE_ENTRY"; else -> "BUY" })
            put("status", "OPEN")
            put("entry_price", position.entryPrice)
            put("stake_idr", position.stakeIdr)
            put("fee_idr", entryFeeIdr)
            put("pnl_idr", 0.0)
            put("opened_at", position.openedAtEpochMs)
            put("entry_reason", position.entryReason)
        })
        recordAudit(
            "TRADE_OPEN",
            "symbol=${position.symbol}|side=${position.entryReason}|entry=${position.entryPrice}|stake=${position.stakeIdr}|sl=${position.stopLossPrice}|tp=${position.takeProfitPrice}|risk_ref=${position.riskReferenceCapitalIdr}",
            position.openedAtEpochMs,
        )
    }

    fun recordTradeClosed(positionId: String, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) {
        require(exitPrice > 0.0)
        require(feeIdr >= 0.0)
        require(exitReason.isNotBlank())
        val position = readableDatabase.rawQuery(
            "SELECT symbol, entry_price, stake_idr, opened_at, entry_reason FROM trades WHERE id = ? LIMIT 1",
            arrayOf(positionId),
        ).use { cursor ->
            if (!cursor.moveToFirst()) null else listOf(
                cursor.getString(0), cursor.getDouble(1), cursor.getDouble(2), cursor.getLong(3), cursor.getString(4),
            )
        } ?: error("trade_not_found:$positionId")
        val updated = writableDatabase.update(
            "trades",
            ContentValues().apply {
                put("status", "CLOSED")
                put("exit_price", exitPrice)
                put("fee_idr", feeIdr)
                put("pnl_idr", pnlIdr)
                put("closed_at", closedAtEpochMs)
                put("exit_reason", exitReason)
            },
            "id = ?",
            arrayOf(positionId),
        )
        check(updated == 1) { "trade_not_found:$positionId" }
        recordAudit(
            "TRADE_CLOSE",
            "symbol=${position[0]}|side=${position[4]}|entry=${position[1]}|exit=$exitPrice|stake=${position[2]}|pnl=$pnlIdr|fee=$feeIdr|exit_reason=$exitReason|opened_at=${position[3]}",
            closedAtEpochMs,
        )
    }

    fun recordAudit(eventType: String, details: String, nowMs: Long = System.currentTimeMillis()) = writableDatabase.insertOrThrow("audit_log", null, ContentValues().apply {
        put("created_at", nowMs)
        put("event_type", eventType)
        put("details", details)
    })

    fun recordSuggestion(symbol: String, action: String, confidence: Double, reason: String, nowMs: Long = System.currentTimeMillis()): Long = writableDatabase.insertOrThrow("suggestions", null, ContentValues().apply {
        put("created_at", nowMs)
        put("symbol", symbol)
        put("action", action)
        put("confidence", confidence)
        put("reason", reason)
    })

    fun recentTrades(limit: Int = 30): List<TradeRow> {
        val rows = mutableListOf<TradeRow>()
        readableDatabase.rawQuery("SELECT id, exchange_id, symbol, side, status, entry_price, exit_price, stake_idr, fee_idr, pnl_idr, opened_at, closed_at, exit_reason, entry_reason FROM trades ORDER BY COALESCE(closed_at, opened_at) DESC LIMIT ?", arrayOf(limit.coerceIn(1, 200).toString())).use { cursor ->
            val id = cursor.getColumnIndexOrThrow("id")
            val exchangeId = cursor.getColumnIndexOrThrow("exchange_id")
            val symbol = cursor.getColumnIndexOrThrow("symbol")
            val side = cursor.getColumnIndexOrThrow("side")
            val status = cursor.getColumnIndexOrThrow("status")
            val entryPrice = cursor.getColumnIndexOrThrow("entry_price")
            val exitPrice = cursor.getColumnIndexOrThrow("exit_price")
            val stake = cursor.getColumnIndexOrThrow("stake_idr")
            val fee = cursor.getColumnIndexOrThrow("fee_idr")
            val pnl = cursor.getColumnIndexOrThrow("pnl_idr")
            val opened = cursor.getColumnIndexOrThrow("opened_at")
            val closed = cursor.getColumnIndexOrThrow("closed_at")
            val reason = cursor.getColumnIndexOrThrow("exit_reason")
            val entryReason = cursor.getColumnIndexOrThrow("entry_reason")
            while (cursor.moveToNext()) rows += TradeRow(
                cursor.getString(id), cursor.getString(exchangeId), cursor.getString(symbol), cursor.getString(side), cursor.getString(status),
                cursor.getDoubleOrNull(entryPrice), cursor.getDoubleOrNull(exitPrice), cursor.getDouble(stake), cursor.getDouble(fee), cursor.getDouble(pnl),
                cursor.getLong(opened), cursor.getLongOrNull(closed), cursor.getStringOrNull(reason), cursor.getString(entryReason),
            )
        }
        return rows
    }

    fun recentSuggestions(limit: Int = 50): List<DecisionRow> {
        val rows = mutableListOf<DecisionRow>()
        readableDatabase.rawQuery("SELECT created_at, symbol, action, confidence, reason FROM suggestions ORDER BY created_at DESC LIMIT ?", arrayOf(limit.coerceIn(1, 200).toString())).use { cursor ->
            val created = cursor.getColumnIndexOrThrow("created_at")
            val symbol = cursor.getColumnIndexOrThrow("symbol")
            val action = cursor.getColumnIndexOrThrow("action")
            val confidence = cursor.getColumnIndexOrThrow("confidence")
            val reason = cursor.getColumnIndexOrThrow("reason")
            while (cursor.moveToNext()) rows += DecisionRow(cursor.getLong(created), cursor.getString(symbol), cursor.getString(action), cursor.getDouble(confidence), cursor.getString(reason))
        }
        return rows
    }

    fun recentAudit(limit: Int = 100): List<AuditRow> {
        val rows = mutableListOf<AuditRow>()
        readableDatabase.rawQuery("SELECT created_at, event_type, details FROM audit_log ORDER BY created_at DESC LIMIT ?", arrayOf(limit.coerceIn(1, 300).toString())).use { cursor ->
            val created = cursor.getColumnIndexOrThrow("created_at")
            val eventType = cursor.getColumnIndexOrThrow("event_type")
            val details = cursor.getColumnIndexOrThrow("details")
            while (cursor.moveToNext()) rows += AuditRow(cursor.getLong(created), cursor.getString(eventType), cursor.getString(details))
        }
        return rows
    }

    fun clearHistory() {
        writableDatabase.beginTransaction()
        try {
            writableDatabase.delete("trades", "status = ?", arrayOf("CLOSED"))
            writableDatabase.delete("suggestions", null, null)
            writableDatabase.delete("audit_log", null, null)
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
    }

    private fun android.database.Cursor.getDoubleOrNull(index: Int): Double? = if (isNull(index)) null else getDouble(index)
    private fun android.database.Cursor.getLongOrNull(index: Int): Long? = if (isNull(index)) null else getLong(index)
    private fun android.database.Cursor.getStringOrNull(index: Int): String? = if (isNull(index)) null else getString(index)

    companion object {
        private const val DB_NAME = "mirei.db"
        private const val DB_VERSION = 3
    }
}

data class TradeRow(
    val id: String,
    val exchangeId: String,
    val symbol: String,
    val side: String,
    val status: String,
    val entryPrice: Double?,
    val exitPrice: Double?,
    val stakeIdr: Double,
    val feeIdr: Double,
    val pnlIdr: Double,
    val openedAtEpochMs: Long,
    val closedAtEpochMs: Long?,
    val exitReason: String?,
    val entryReason: String = "entry_filled",
)

data class DecisionRow(val createdAtEpochMs: Long, val symbol: String, val action: String, val confidence: Double, val reason: String)
data class AuditRow(val createdAtEpochMs: Long, val eventType: String, val details: String)
