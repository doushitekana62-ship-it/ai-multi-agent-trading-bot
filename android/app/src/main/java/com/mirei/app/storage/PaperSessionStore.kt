package com.mirei.app.storage

import android.content.Context
import com.mirei.app.execution.PaperPosition
import org.json.JSONArray
import org.json.JSONObject

data class PaperSessionSnapshot(
    val active: Boolean,
    val sessionCreatedAtEpochMs: Long,
    val runStartedAtEpochMs: Long,
    val runStoppedAtEpochMs: Long,
    val timestampResetAtEpochMs: Long,
    val symbol: String,
    val exchangeId: String,
    val managedSymbols: List<String>,
    val availableBalanceIdr: Double,
    val dailyPnlIdr: Double,
    val consecutiveLosses: Int,
    val holdingsSeeded: Boolean,
    val positions: List<PaperPosition>,
    val buyDecisionCount: Int,
    val holdDecisionCount: Int,
    val sellDecisionCount: Int,
)

class PaperSessionStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): PaperSessionSnapshot? {
        val raw = prefs.getString(KEY_STATE, null) ?: return null
        return runCatching {
            val root = JSONObject(raw)
            val positions = mutableListOf<PaperPosition>()
            val array = root.optJSONArray("positions") ?: JSONArray()
            for (i in 0 until array.length()) {
                val item = array.getJSONObject(i)
                positions += PaperPosition(
                    id = item.getString("id"),
                    exchangeId = item.getString("exchange"),
                    symbol = item.getString("symbol"),
                    stakeIdr = item.getDouble("stake"),
                    entryPrice = item.getDouble("entry"),
                    stopLossPrice = item.getDouble("sl"),
                    takeProfitPrice = item.getDouble("tp"),
                    trailingActivationPrice = item.getDouble("trailing"),
                    openedAtEpochMs = item.getLong("opened"),
                    entryReason = item.optString("reason", "entry_filled"),
                )
            }
            PaperSessionSnapshot(
                active = root.optBoolean("active", false),
                sessionCreatedAtEpochMs = root.optLong("sessionCreated", 0L),
                runStartedAtEpochMs = root.optLong("runStarted", 0L),
                runStoppedAtEpochMs = root.optLong("runStopped", 0L),
                timestampResetAtEpochMs = root.optLong("timestampReset", 0L),
                symbol = root.optString("symbol", "BTC/IDR"),
                exchangeId = root.optString("exchange", "indodax"),
                managedSymbols = root.optString("managedSymbols", "BTC/IDR").split(',').filter { it.isNotBlank() },
                availableBalanceIdr = root.optDouble("balance", 0.0),
                dailyPnlIdr = root.optDouble("dailyPnl", 0.0),
                consecutiveLosses = root.optInt("consecutiveLosses", 0),
                holdingsSeeded = root.optBoolean("holdingsSeeded", false),
                positions = positions,
                buyDecisionCount = root.optInt("buyCount", 0),
                holdDecisionCount = root.optInt("holdCount", 0),
                sellDecisionCount = root.optInt("sellCount", 0),
            )
        }.getOrNull()
    }

    fun save(snapshot: PaperSessionSnapshot) {
        val root = JSONObject().apply {
            put("active", snapshot.active)
            put("sessionCreated", snapshot.sessionCreatedAtEpochMs)
            put("runStarted", snapshot.runStartedAtEpochMs)
            put("runStopped", snapshot.runStoppedAtEpochMs)
            put("timestampReset", snapshot.timestampResetAtEpochMs)
            put("symbol", snapshot.symbol)
            put("exchange", snapshot.exchangeId)
            put("managedSymbols", snapshot.managedSymbols.joinToString(","))
            put("balance", snapshot.availableBalanceIdr)
            put("dailyPnl", snapshot.dailyPnlIdr)
            put("consecutiveLosses", snapshot.consecutiveLosses)
            put("holdingsSeeded", snapshot.holdingsSeeded)
            put("buyCount", snapshot.buyDecisionCount)
            put("holdCount", snapshot.holdDecisionCount)
            put("sellCount", snapshot.sellDecisionCount)
            put("positions", JSONArray().apply {
                snapshot.positions.forEach { position -> put(JSONObject().apply {
                    put("id", position.id)
                    put("exchange", position.exchangeId)
                    put("symbol", position.symbol)
                    put("stake", position.stakeIdr)
                    put("entry", position.entryPrice)
                    put("sl", position.stopLossPrice)
                    put("tp", position.takeProfitPrice)
                    put("trailing", position.trailingActivationPrice)
                    put("opened", position.openedAtEpochMs)
                    put("reason", position.entryReason)
                }) }
            })
        }
        prefs.edit().putString(KEY_STATE, root.toString()).apply()
    }

    fun clearSession() = prefs.edit().remove(KEY_STATE).apply()

    companion object {
        private const val PREFS = "mirei_paper_session"
        private const val KEY_STATE = "state"
    }
}
