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
                val sl = fields.getOrNull(0)?.toDoubleOrNull()
                val target = fields.getOrNull(1)?.toDoubleOrNull()
                val basis = fields.getOrNull(2)?.let { RiskReferenceMode.valueOf(it) } ?: RiskReferenceMode.ENTRY_PRICE
                if (sl != null && target != null && sl > 0.0 && target > 0.0) {
                    parsed[parts[0]] = PositionTradeConfig(sl, target, basis)
                }
            }
        }
        profiles = parsed
    }

    fun get(symbol: String): PositionTradeConfig? = profiles[symbol]
    fun snapshot(): Map<String, PositionTradeConfig> = profiles
}
