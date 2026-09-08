package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.sqrt

/** Public market-data adapter. It never uses API credentials and never places orders. */
class IndodaxMarketDataSource(
    private val baseUrl: String = "https://indodax.com/api",
    private val timeoutMs: Int = 3_000,
) : PaperMarketDataSource {
    override fun snapshot(symbol: String): MarketSnapshot? {
        val pair = symbol.lowercase().replace("/", "_")
        val startedAt = System.currentTimeMillis()
        val ticker = getJsonObject("$baseUrl/$pair/ticker")?.optJSONObject("ticker") ?: return null
        val price = ticker.optString("last").toDoubleOrNull() ?: return null
        if (price <= 0.0) return null

        val high = ticker.optString("high").toDoubleOrNull() ?: price
        val low = ticker.optString("low").toDoubleOrNull() ?: price
        val trades = getJsonArray("$baseUrl/$pair/trades")
        val tradePrices = trades?.let { prices(it) }.orEmpty()
        val momentum = if (tradePrices.size >= 2) {
            ((tradePrices.first() - tradePrices.last()) / tradePrices.last()) * 100.0
        } else {
            0.0
        }
        val volatility = if (tradePrices.size >= 2) standardDeviationPercent(tradePrices) else ((high - low) / price) * 100.0
        val ageMs = ticker.optLong("server_time", 0L).let { serverTime ->
            if (serverTime <= 0L) 0L else startedAt - if (serverTime < 10_000_000_000L) serverTime * 1_000L else serverTime
        }
        val fresh = ageMs <= 30_000L || ageMs == 0L

        return MarketSnapshot(
            symbol = symbol,
            price = price,
            momentumPercent = momentum,
            volatilityPercent = volatility.coerceAtLeast(0.01),
            sentimentScore = 0.0,
            forecastConfidence = 0.65,
            dataFresh = fresh,
        )
    }

    private fun getJsonObject(url: String): JSONObject? = runCatching { JSONObject(get(url)) }.getOrNull()
    private fun getJsonArray(url: String): JSONArray? = runCatching { JSONArray(get(url)) }.getOrNull()

    private fun get(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = timeoutMs
        connection.readTimeout = timeoutMs
        connection.requestMethod = "GET"
        connection.setRequestProperty("Accept", "application/json")
        return try {
            if (connection.responseCode !in 200..299) throw IllegalStateException("market_http_${connection.responseCode}")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun prices(trades: JSONArray): List<Double> = buildList {
        for (index in 0 until trades.length()) {
            val price = trades.optJSONObject(index)?.optString("price")?.toDoubleOrNull()
            if (price != null && price > 0.0) add(price)
        }
    }

    private fun standardDeviationPercent(prices: List<Double>): Double {
        val mean = prices.average()
        if (mean <= 0.0) return 0.0
        val variance = prices.sumOf { (it - mean) * (it - mean) } / prices.size
        return sqrt(variance) / mean * 100.0
    }
}
