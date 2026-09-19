package com.mirei.app.storage

import android.content.Context
import com.mirei.app.core.MireiCycle
import com.mirei.app.core.MireiCycleState
import com.mirei.app.core.MireiDecisionAction
import com.mirei.app.core.PositionTradeConfig
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.execution.PaperPosition
import org.json.JSONArray
import org.json.JSONObject

data class PaperSessionSnapshot(
    val active: Boolean,
    val sessionCreatedAtEpochMs: Long,
    val runStartedAtEpochMs: Long,
    val runStoppedAtEpochMs: Long,
    val timestampResetAtEpochMs: Long,
    val sessionOpeningCapitalIdr: Double = 0.0,
    val symbol: String,
    val exchangeId: String,
    val managedSymbols: List<String>,
    val availableBalanceIdr: Double,
    val dailyPnlIdr: Double,
    val consecutiveLosses: Int,
    val holdingsSeeded: Boolean,
    val positions: List<PaperPosition>,
    val buyDecisionCount: Int = 0,
    val holdDecisionCount: Int = 0,
    val sellDecisionCount: Int = 0,
    val initialCapitalBySymbol: Map<String, Double> = emptyMap(),
    val positionProfiles: Map<String, PositionTradeConfig> = emptyMap(),
    val mireiCycles: Map<String, MireiCycle> = emptyMap(),
    val pausedSymbols: Set<String> = emptySet(),
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
                val riskReferenceMode = runCatching {
                    RiskReferenceMode.valueOf(item.optString("riskReferenceMode", RiskReferenceMode.ENTRY_PRICE.name))
                }.getOrDefault(RiskReferenceMode.ENTRY_PRICE)
                val target = item.optDouble("manualNetProfitTargetIdr", 0.0).takeIf { it > 0.0 }
                positions += PaperPosition(
                    item.getString("id"),
                    item.getString("exchange"),
                    item.getString("symbol"),
                    item.getDouble("stake"),
                    item.getDouble("entry"),
                    item.getDouble("sl"),
                    item.getDouble("tp"),
                    item.getDouble("trailing"),
                    item.getLong("opened"),
                    item.optString("reason", "entry_filled"),
                    riskReferenceMode,
                    item.optDouble("riskReferenceCapital", item.optDouble("stake", 0.0)),
                    com.mirei.app.core.TakeProfitMode.MANUAL_NET_IDR,
                    target,
                    profileFromJson(item.optJSONObject("profile")),
                )
            }

            val initialCapitalBySymbol = linkedMapOf<String, Double>()
            root.optJSONObject("initialCapitalBySymbol")?.keys()?.forEach { key ->
                initialCapitalBySymbol[key] = root.optJSONObject("initialCapitalBySymbol")?.optDouble(key, 0.0) ?: 0.0
            }

            val mireiCycles = linkedMapOf<String, MireiCycle>()
            root.optJSONObject("mireiCycles")?.keys()?.forEach { key ->
                root.optJSONObject("mireiCycles")?.optJSONObject(key)?.let { item ->
                    runCatching {
                        mireiCycles[key] = MireiCycle(
                            cycleId = item.optString("cycleId", key),
                            symbol = item.optString("symbol", key),
                            initialCapitalIdr = item.optDouble("initialCapitalIdr", 0.0),
                            initialBuyPrice = item.optDouble("initialBuyPrice", 0.0),
                            reentryCount = item.optInt("reentryCount", 0),
                            sequence = item.optInt("sequence", 1),
                            state = MireiCycleState.valueOf(item.optString("state", MireiCycleState.HOLDING.name)),
                            lastDecision = MireiDecisionAction.valueOf(item.optString("lastDecision", MireiDecisionAction.HOLD.name)),
                            lastDecisionReason = item.optString("lastDecisionReason", ""),
                            lastTransitionAtEpochMs = item.optLong("lastTransitionAtEpochMs", 0L),
                        )
                    }
                }
            }

            val positionProfiles = linkedMapOf<String, PositionTradeConfig>()
            root.optJSONObject("positionProfiles")?.keys()?.forEach { key ->
                profileFromJson(root.optJSONObject("positionProfiles")?.optJSONObject(key))?.let { positionProfiles[key] = it }
            }

            PaperSessionSnapshot(
                active = root.optBoolean("active", false),
                sessionCreatedAtEpochMs = root.optLong("sessionCreated", 0L),
                runStartedAtEpochMs = root.optLong("runStarted", 0L),
                runStoppedAtEpochMs = root.optLong("runStopped", 0L),
                timestampResetAtEpochMs = root.optLong("timestampReset", 0L),
                sessionOpeningCapitalIdr = root.optDouble("sessionOpeningCapitalIdr", 0.0),
                symbol = root.optString("symbol", "BTC/IDR"),
                exchangeId = root.optString("exchange", "indodax"),
                managedSymbols = root.optString("managedSymbols", "BTC/IDR").split(',').filter { it.isNotBlank() },
                availableBalanceIdr = root.optDouble("balance", 0.0),
                dailyPnlIdr = root.optDouble("dailyPnl", 0.0),
                consecutiveLosses = root.optInt("consecutiveLosses", 0),
                holdingsSeeded = root.optBoolean("holdingsSeeded", false),
                positions = positions,
                initialCapitalBySymbol = initialCapitalBySymbol,
                positionProfiles = positionProfiles,
                mireiCycles = mireiCycles,
                pausedSymbols = root.optString("pausedSymbols", "").split(',').filter { it.isNotBlank() }.toSet(),
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
            put("sessionOpeningCapitalIdr", snapshot.sessionOpeningCapitalIdr)
            put("symbol", snapshot.symbol)
            put("exchange", snapshot.exchangeId)
            put("managedSymbols", snapshot.managedSymbols.joinToString(","))
            put("balance", snapshot.availableBalanceIdr)
            put("dailyPnl", snapshot.dailyPnlIdr)
            put("consecutiveLosses", snapshot.consecutiveLosses)
            put("holdingsSeeded", snapshot.holdingsSeeded)
            put("initialCapitalBySymbol", JSONObject().apply {
                snapshot.initialCapitalBySymbol.forEach { (symbol, amount) -> put(symbol, amount) }
            })
            put("positionProfiles", JSONObject().apply {
                snapshot.positionProfiles.forEach { (symbol, profile) -> put(symbol, profileToJson(profile)) }
            })
            put("pausedSymbols", snapshot.pausedSymbols.joinToString(","))
            put("mireiCycles", JSONObject().apply {
                snapshot.mireiCycles.forEach { (symbol, cycle) ->
                    put(symbol, JSONObject().apply {
                        put("cycleId", cycle.cycleId)
                        put("symbol", cycle.symbol)
                        put("initialCapitalIdr", cycle.initialCapitalIdr)
                        put("initialBuyPrice", cycle.initialBuyPrice)
                        put("reentryCount", cycle.reentryCount)
                        put("sequence", cycle.sequence)
                        put("state", cycle.state.name)
                        put("lastDecision", cycle.lastDecision.name)
                        put("lastDecisionReason", cycle.lastDecisionReason)
                        put("lastTransitionAtEpochMs", cycle.lastTransitionAtEpochMs)
                    })
                }
            })
            put("positions", JSONArray().apply {
                snapshot.positions.forEach { position ->
                    put(JSONObject().apply {
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
                        put("riskReferenceMode", position.riskReferenceMode.name)
                        put("riskReferenceCapital", position.riskReferenceCapitalIdr)
                        if (position.manualNetProfitTargetIdr != null) put("manualNetProfitTargetIdr", position.manualNetProfitTargetIdr)
                        if (position.positionProfile != null) put("profile", profileToJson(position.positionProfile))
                    })
                }
            })
        }
        prefs.edit().putString(KEY_STATE, root.toString()).commit()
    }

    private fun profileToJson(profile: PositionTradeConfig): JSONObject = JSONObject().apply {
        put("stopLossPercent", profile.stopLossPercent ?: JSONObject.NULL)
        put("manualNetProfitTargetIdr", profile.manualNetProfitTargetIdr ?: JSONObject.NULL)
        put("riskReferenceMode", profile.riskReferenceMode?.name ?: JSONObject.NULL)
    }

    private fun profileFromJson(item: JSONObject?): PositionTradeConfig? = item?.let {
        runCatching {
            PositionTradeConfig(
                stopLossPercent = if (it.isNull("stopLossPercent")) null else it.optDouble("stopLossPercent"),
                manualNetProfitTargetIdr = if (it.isNull("manualNetProfitTargetIdr")) null else it.optDouble("manualNetProfitTargetIdr"),
                riskReferenceMode = it.optString("riskReferenceMode").takeIf { value -> value.isNotBlank() && value != "null" }
                    ?.let { value -> RiskReferenceMode.valueOf(value) },
            )
        }.getOrNull()
    }

    fun clearSession() = prefs.edit().remove(KEY_STATE).commit()

    companion object {
        private const val PREFS = "mirei_paper_session"
        private const val KEY_STATE = "state"
    }
}
