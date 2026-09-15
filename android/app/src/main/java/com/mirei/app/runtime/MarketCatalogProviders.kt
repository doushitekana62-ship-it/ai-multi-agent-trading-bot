package com.mirei.app.runtime

import com.mirei.app.core.AssetClass
import com.mirei.app.core.ExecutionCostProfile
import com.mirei.app.core.MarketInstrument
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

interface MarketCatalogProvider {
    val providerId: String
    fun discover(): List<MarketInstrument>
}

/** Discovers IDR instruments exposed by the public Indodax ticker catalog. */
class IndodaxMarketCatalogProvider(
    private val baseUrl: String = "https://indodax.com/api",
    private val timeoutMs: Int = 3_000,
) : MarketCatalogProvider {
    override val providerId: String = "indodax"

    override fun discover(): List<MarketInstrument> = runCatching {
        val json = JSONObject(get("$baseUrl/tickers"))
        val tickers = json.optJSONObject("tickers") ?: return emptyList()
        buildList {
            val keys = tickers.keys()
            while (keys.hasNext()) {
                val raw = keys.next().lowercase()
                if (!raw.endsWith("_idr")) continue
                val base = raw.removeSuffix("_idr").trim()
                if (base.isBlank()) continue
                val symbol = "${base.uppercase()}/IDR"
                add(MarketInstrument(symbol, base.uppercase(), AssetClass.CRYPTO, "IDR", providerId = providerId, executionCosts = ExecutionCostProfile.INDODAX_IDR_TAKER))
            }
        }.distinctBy { it.symbol }.sortedBy { it.symbol }
    }.getOrDefault(emptyList())

    private fun get(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = timeoutMs
        connection.readTimeout = timeoutMs
        connection.requestMethod = "GET"
        connection.setRequestProperty("Accept", "application/json")
        return try {
            if (connection.responseCode !in 200..299) throw IllegalStateException("market_catalog_http_${connection.responseCode}")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally { connection.disconnect() }
    }
}
