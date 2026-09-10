package com.mirei.app.storage

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.mirei.app.execution.PaperPosition

class MireiDatabase(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                exchange_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                stake_idr REAL NOT NULL,
                fee_idr REAL NOT NULL DEFAULT 0,
                pnl_idr REAL NOT NULL DEFAULT 0,
                opened_at INTEGER NOT NULL,
                closed_at INTEGER,
                exit_reason TEXT
            )"""
        )
        db.execSQL("""CREATE TABLE suggestions (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, symbol TEXT NOT NULL, action TEXT NOT NULL, confidence REAL NOT NULL, reason TEXT NOT NULL, outcome TEXT)""")
        db.execSQL("""CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL, event_type TEXT NOT NULL, details TEXT NOT NULL)""")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) db.execSQL("ALTER TABLE trades ADD COLUMN exit_reason TEXT")
    }

    fun recordTradeOpened(position: PaperPosition, entryFeeIdr: Double) {
        require(entryFeeIdr >= 0.0)
        writableDatabase.insertOrThrow("trades", null, ContentValues().apply {
            put("id", position.id); put("exchange_id", position.exchangeId); put("symbol", position.symbol); put("side", "BUY"); put("status", "OPEN")
            put("entry_price", position.entryPrice); put("stake_idr", position.stakeIdr); put("fee_idr", entryFeeIdr); put("pnl_idr", 0.0); put("opened_at", position.openedAtEpochMs)
        })
    }

    fun recordTradeClosed(positionId: String, exitPrice: Double, feeIdr: Double, pnlIdr: Double, closedAtEpochMs: Long, exitReason: String) {
        require(exitPrice > 0.0); require(feeIdr >= 0.0); require(exitReason.isNotBlank())
        val updated = writableDatabase.update("trades", ContentValues().apply {
            put("status", "CLOSED"); put("exit_price", exitPrice); put("fee_idr", feeIdr); put("pnl_idr", pnlIdr); put("closed_at", closedAtEpochMs); put("exit_reason", exitReason)
        }, "id = ?", arrayOf(positionId))
        check(updated == 1) { "trade_not_found:$positionId" }
    }

    fun recordAudit(eventType: String, details: String, nowMs: Long = System.currentTimeMillis()) = writableDatabase.insertOrThrow("audit_log", null, ContentValues().apply { put("created_at", nowMs); put("event_type", eventType); put("details", details) })

    fun recordSuggestion(symbol: String, action: String, confidence: Double, reason: String, nowMs: Long = System.currentTimeMillis()): Long = writableDatabase.insertOrThrow("suggestions", null, ContentValues().apply {
        put("created_at", nowMs); put("symbol", symbol); put("action", action); put("confidence", confidence); put("reason", reason)
    })

    fun recentTrades(limit: Int = 30): List<TradeRow> {
        val rows = mutableListOf<TradeRow>()
        readableDatabase.rawQuery("SELECT id, exchange_id, symbol, side, status, entry_price, exit_price, stake_idr, fee_idr, pnl_idr, opened_at, closed_at, exit_reason FROM trades ORDER BY COALESCE(closed_at, opened_at) DESC LIMIT ?", arrayOf(limit.coerceIn(1, 200).toString())).use { cursor ->
            val idx = cursor.columnIndexes()
            while (cursor.moveToNext()) rows += TradeRow(
                id = cursor.getString(idx("id")), exchangeId = cursor.getString(idx("exchange_id")), symbol = cursor.getString(idx("symbol")), side = cursor.getString(idx("side")),
                status = cursor.getString(idx("status")), entryPrice = cursor.getDoubleOrNull(idx("entry_price")), exitPrice = cursor.getDoubleOrNull(idx("exit_price")), stakeIdr = cursor.getDouble(idx("stake_idr")),
                feeIdr = cursor.getDouble(idx("fee_idr")), pnlIdr = cursor.getDouble(idx("pnl_idr")), openedAtEpochMs = cursor.getLong(idx("opened_at")), closedAtEpochMs = cursor.getLongOrNull(idx("closed_at")), exitReason = cursor.getStringOrNull(idx("exit_reason")),
            )
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
        } finally { writableDatabase.endTransaction() }
    }

    private fun android.database.Cursor.columnIndexes(): Map<String, Int> = buildMap { for (i in 0 until columnCount) put(getColumnName(i), i) }
    private fun android.database.Cursor.getDoubleOrNull(index: Int): Double? = if (isNull(index)) null else getDouble(index)
    private fun android.database.Cursor.getLongOrNull(index: Int): Long? = if (isNull(index)) null else getLong(index)
    private fun android.database.Cursor.getStringOrNull(index: Int): String? = if (isNull(index)) null else getString(index)
    private fun Map<String, Int>.get(key: String): Int = checkNotNull(this[key])

    companion object { private const val DB_NAME = "mirei.db"; private const val DB_VERSION = 2 }
}

data class TradeRow(
    val id: String, val exchangeId: String, val symbol: String, val side: String, val status: String, val entryPrice: Double?, val exitPrice: Double?, val stakeIdr: Double,
    val feeIdr: Double, val pnlIdr: Double, val openedAtEpochMs: Long, val closedAtEpochMs: Long?, val exitReason: String?,
)
