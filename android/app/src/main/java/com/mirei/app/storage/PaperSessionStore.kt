package com.mirei.app.storage

import android.content.Context
import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.PositionTradeConfig
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TakeProfitMode
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
    val initialCapitalBySymbol: Map<String, Double> = emptyMap(),
    val positionProfiles: Map<String, PositionTradeConfig> = emptyMap(),
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
                val storedMode = runCatching { RiskReferenceMode.valueOf(item.optString("riskReferenceMode", RiskReferenceMode.ENTRY_PRICE.name)) }.getOrDefault(RiskReferenceMode.ENTRY_PRICE)
                val storedTpMode = runCatching { TakeProfitMode.valueOf(item.optString("takeProfitMode", TakeProfitMode.MODE.name)) }.getOrDefault(TakeProfitMode.MODE)
                val storedManualTarget = if (item.has("manualNetProfitTargetIdr") && !item.isNull("manualNetProfitTargetIdr")) item.optDouble("manualNetProfitTargetIdr", 0.0).takeIf { it > 0.0 } else null
                positions += PaperPosition(item.getString("id"), item.getString("exchange"), item.getString("symbol"), item.getDouble("stake"), item.getDouble("entry"), item.getDouble("sl"), item.getDouble("tp"), item.getDouble("trailing"), item.getLong("opened"), item.optString("reason", "entry_filled"), storedMode, item.optDouble("riskReferenceCapital", item.optDouble("stake", 0.0)), storedTpMode, storedManualTarget, profileFromJson(item.optJSONObject("profile")))
            }
            val capitalObject = root.optJSONObject("initialCapitalBySymbol")
            val initialCapitalBySymbol = linkedMapOf<String, Double>()
            if (capitalObject != null) capitalObject.keys().forEach { key -> initialCapitalBySymbol[key] = capitalObject.optDouble(key, 0.0) }
            val profileObject = root.optJSONObject("positionProfiles")
            val positionProfiles = linkedMapOf<String, PositionTradeConfig>()
            if (profileObject != null) profileObject.keys().forEach { key -> profileFromJson(profileObject.optJSONObject(key))?.let { positionProfiles[key] = it } }
            PaperSessionSnapshot(root.optBoolean("active", false), root.optLong("sessionCreated", 0L), root.optLong("runStarted", 0L), root.optLong("runStopped", 0L), root.optLong("timestampReset", 0L), root.optString("symbol", "BTC/IDR"), root.optString("exchange", "indodax"), root.optString("managedSymbols", "BTC/IDR").split(',').filter { it.isNotBlank() }, root.optDouble("balance", 0.0), root.optDouble("dailyPnl", 0.0), root.optInt("consecutiveLosses", 0), root.optBoolean("holdingsSeeded", false), positions, root.optInt("buyCount", 0), root.optInt("holdCount", 0), root.optInt("sellCount", 0), initialCapitalBySymbol, positionProfiles)
        }.getOrNull()
    }

    fun save(snapshot: PaperSessionSnapshot) {
        val root = JSONObject().apply {
            put("active", snapshot.active); put("sessionCreated", snapshot.sessionCreatedAtEpochMs); put("runStarted", snapshot.runStartedAtEpochMs); put("runStopped", snapshot.runStoppedAtEpochMs); put("timestampReset", snapshot.timestampResetAtEpochMs); put("symbol", snapshot.symbol); put("exchange", snapshot.exchangeId); put("managedSymbols", snapshot.managedSymbols.joinToString(",")); put("balance", snapshot.availableBalanceIdr); put("dailyPnl", snapshot.dailyPnlIdr); put("consecutiveLosses", snapshot.consecutiveLosses); put("holdingsSeeded", snapshot.holdingsSeeded); put("buyCount", snapshot.buyDecisionCount); put("holdCount", snapshot.holdDecisionCount); put("sellCount", snapshot.sellDecisionCount)
            put("initialCapitalBySymbol", JSONObject().apply { snapshot.initialCapitalBySymbol.forEach { (symbol, amount) -> put(symbol, amount) } })
            put("positionProfiles", JSONObject().apply { snapshot.positionProfiles.forEach { (symbol, profile) -> put(symbol, profileToJson(profile)) } })
            put("positions", JSONArray().apply { snapshot.positions.forEach { position -> put(JSONObject().apply { put("id", position.id); put("exchange", position.exchangeId); put("symbol", position.symbol); put("stake", position.stakeIdr); put("entry", position.entryPrice); put("sl", position.stopLossPrice); put("tp", position.takeProfitPrice); put("trailing", position.trailingActivationPrice); put("opened", position.openedAtEpochMs); put("reason", position.entryReason); put("riskReferenceMode", position.riskReferenceMode.name); put("riskReferenceCapital", position.riskReferenceCapitalIdr); put("takeProfitMode", position.takeProfitMode.name); if (position.manualNetProfitTargetIdr != null) put("manualNetProfitTargetIdr", position.manualNetProfitTargetIdr); if (position.positionProfile != null) put("profile", profileToJson(position.positionProfile)) }) } })
        }
        prefs.edit().putString(KEY_STATE, root.toString()).commit()
    }

    private fun profileToJson(profile: PositionTradeConfig): JSONObject = JSONObject().apply { put("mode", profile.mode?.name ?: JSONObject.NULL); put("manualRiskMode", profile.manualRiskMode.name); put("stopLossPercent", profile.stopLossPercent ?: JSONObject.NULL); put("takeProfitMode", profile.takeProfitMode.name); put("manualTakeProfitPercent", profile.manualTakeProfitPercent ?: JSONObject.NULL); put("manualNetProfitTargetIdr", profile.manualNetProfitTargetIdr ?: JSONObject.NULL); put("riskReferenceMode", profile.riskReferenceMode?.name ?: JSONObject.NULL) }
    private fun profileFromJson(item: JSONObject?): PositionTradeConfig? = item?.let { runCatching { PositionTradeConfig(mode = it.optString("mode").takeIf { s -> s.isNotBlank() && s != "null" }?.let { s -> ScalpingMode.valueOf(s) }, manualRiskMode = ManualRiskMode.valueOf(it.optString("manualRiskMode", ManualRiskMode.AUTO.name)), stopLossPercent = if (it.isNull("stopLossPercent")) null else it.optDouble("stopLossPercent"), takeProfitMode = TakeProfitMode.valueOf(it.optString("takeProfitMode", TakeProfitMode.MODE.name)), manualTakeProfitPercent = if (it.isNull("manualTakeProfitPercent")) null else it.optDouble("manualTakeProfitPercent"), manualNetProfitTargetIdr = if (it.isNull("manualNetProfitTargetIdr")) null else it.optDouble("manualNetProfitTargetIdr"), riskReferenceMode = it.optString("riskReferenceMode").takeIf { s -> s.isNotBlank() && s != "null" }?.let { s -> RiskReferenceMode.valueOf(s) }) }.getOrNull() }
    fun clearSession() = prefs.edit().remove(KEY_STATE).commit()
    companion object { private const val PREFS = "mirei_paper_session"; private const val KEY_STATE = "state" }
}
