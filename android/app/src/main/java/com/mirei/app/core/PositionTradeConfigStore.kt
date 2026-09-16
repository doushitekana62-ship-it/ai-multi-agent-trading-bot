package com.mirei.app.core

import android.content.Context

object PositionTradeConfigStore {
    @Volatile private var profiles: Map<String, PositionTradeConfig> = emptyMap()

    fun reload(context: Context) {
        val prefs = context.getSharedPreferences("mirei_settings", Context.MODE_PRIVATE)
        val raw = prefs.getString("position_profiles", "").orEmpty()
        val parsed = linkedMapOf<String, PositionTradeConfig>()
        raw.split(';').forEach { entry ->
            val parts = entry.split('|')
            if (parts.size < 2) return@forEach
            val fields = parts[1].split(',')
            runCatching {
                val mode = ScalpingMode.valueOf(fields[0])
                val manual = fields[1].toBoolean()
                val sl = fields[2].toDouble()
                val tpMode = TakeProfitMode.valueOf(fields[3])
                val tpPercent = fields[4].toDouble()
                val netTarget = fields[5].toDouble()
                val basis = RiskReferenceMode.valueOf(fields[6])
                parsed[parts[0]] = PositionTradeConfig(
                    mode = mode,
                    manualRiskMode = if (manual) ManualRiskMode.MANUAL else ManualRiskMode.AUTO,
                    stopLossPercent = if (manual) sl else null,
                    takeProfitMode = if (manual) tpMode else TakeProfitMode.MODE,
                    manualTakeProfitPercent = if (manual && tpMode == TakeProfitMode.MANUAL_PERCENT) tpPercent else null,
                    manualNetProfitTargetIdr = if (manual && tpMode == TakeProfitMode.MANUAL_NET_IDR) netTarget else null,
                    riskReferenceMode = basis,
                )
            }
        }
        profiles = parsed
    }

    fun get(symbol: String): PositionTradeConfig? = profiles[symbol]
    fun snapshot(): Map<String, PositionTradeConfig> = profiles
}
