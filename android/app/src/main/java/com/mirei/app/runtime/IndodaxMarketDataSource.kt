package com.mirei.app.runtime

import com.mirei.app.core.MarketSnapshot
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.abs
import kotlin.math.sqrt

/** Public market-data adapter. It never uses API credentials and never places orders. */
class IndodaxMarketDataSource(
    private val baseUrl: String = "https://indodax.com/api",
    private val timeoutMs: Int = 3_000,
) : PaperMarketDataSource {
    private data class Sample(val epochMs: Long, val price: Double)
    private data class Trade(val epochMs: Long, val price: Double, val amount: Double, val type: String)

    private val priceHistory = mutableMapOf<String, MutableList<Sample>>()
    private val lastPrices = mutableMapOf<String, Double>()

    override fun snapshot(symbol: String): MarketSnapshot? {
        val pair = symbol.lowercase().replace("/", "_")
        val requestedAt = System.currentTimeMillis()
        val ticker = getJsonObject("$baseUrl/$pair/ticker")?.optJSONObject("ticker") ?: return null
        val price = ticker.optString("last").toDoubleOrNull() ?: return null
        if (price <= 0.0) return null

        val high = ticker.optString("high").toDoubleOrNull()?.takeIf { it > 0.0 } ?: price
        val low = ticker.optString("low").toDoubleOrNull()?.takeIf { it > 0.0 } ?: price
        val volume24h = firstPositive(
            ticker.optString("vol_idr").toDoubleOrNull(),
            ticker.optString("volume").toDoubleOrNull(),
            ticker.optString("vol").toDoubleOrNull(),
        )
        val trades = getJsonArray("$baseUrl/$pair/trades")?.let(::parseTrades).orEmpty()
        val tradePrices = trades.map { it.price }
        val tradeMomentum = momentumFromTrades(trades)
        val tradeFlowPercent = tradeFlowPercent(trades)
        val buyVolume = trades.filter { it.type == "buy" }.sumOf { it.amount }
        val sellVolume = trades.filter { it.type == "sell" }.sumOf { it.amount }

        val previousPrice = lastPrices[pair]
        val immediateChange = previousPrice?.takeIf { it > 0.0 }?.let { ((price - it) / it) * 100.0 } ?: 0.0
        lastPrices[pair] = price
        val history = priceHistory.getOrPut(pair) { mutableListOf() }
        history += Sample(requestedAt, price)
        val cutoff = requestedAt - 15 * 60_000L
        history.removeAll { it.epochMs < cutoff }
        val change1m = percentChangeFrom(history, requestedAt - 60_000L)
        val change5m = percentChangeFrom(history, requestedAt - 5 * 60_000L)
        val change15m = percentChangeFrom(history, requestedAt - 15 * 60_000L)

        val momentum = when {
            abs(change1m) > 0.000001 -> (change1m * 0.70 + immediateChange * 0.30)
            abs(tradeMomentum) > 0.000001 -> tradeMomentum
            else -> immediateChange
        }
        val volatility = if (tradePrices.size >= 2) {
            standardDeviationPercent(tradePrices)
        } else {
            ((high - low) / price) * 100.0
        }.coerceAtLeast(0.01)
        val rangePosition = if (high > low) ((price - low) / (high - low) * 2.0 - 1.0) else 0.0
        val trendScore = (momentum * 20.0 + change5m * 8.0 + tradeFlowPercent * 0.45 + rangePosition * 10.0)
            .coerceIn(-100.0, 100.0)
        val sentiment = (tradeFlowPercent * 0.70 + change5m * 6.0 + rangePosition * 20.0).coerceIn(-100.0, 100.0)
        val forecastConfidence = (0.50 + abs(trendScore) / 200.0).coerceIn(0.50, 0.95)

        val serverTimeRaw = ticker.optLong("server_time", 0L)
        val serverTimeMs = toEpochMs(serverTimeRaw)
        val sourceAgeMs = if (serverTimeMs > 0L) (requestedAt - serverTimeMs).coerceAtLeast(0L) else 0L
        val fresh = sourceAgeMs <= 30_000L || serverTimeMs == 0L
        val bestBid = bestPrice(getJsonObject("$baseUrl/$pair/depth")?.optJSONArray("buy"), highest = true) ?: price
        val bestAsk = bestPrice(getJsonObject("$baseUrl/$pair/depth")?.optJSONArray("sell"), highest = false) ?: price
        val spreadPercent = if (bestBid > 0.0 && bestAsk >= bestBid) ((bestAsk - bestBid) / ((bestAsk + bestBid) / 2.0)) * 100.0 else 0.0
        val lastTradeEpochMs = trades.maxOfOrNull { it.epochMs } ?: serverTimeMs

        return MarketSnapshot(
            symbol = symbol,
            price = price,
            momentumPercent = momentum,
            volatilityPercent = volatility,
            sentimentScore = sentiment,
            forecastConfidence = forecastConfidence,
            dataFresh = fresh,
            bidPrice = bestBid,
            askPrice = bestAsk,
            high24h = high,
            low24h = low,
            volume24h = volume24h,
            spreadPercent = spreadPercent,
            changeSinceLastTickPercent = immediateChange,
            change1mPercent = change1m,
            change5mPercent = change5m,
            change15mPercent = change15m,
            tradeFlowPercent = tradeFlowPercent,
            tradeCount = trades.size,
            buyVolume = buyVolume,
            sellVolume = sellVolume,
            lastTradeEpochMs = lastTradeEpochMs,
            snapshotEpochMs = requestedAt,
            sourceAgeMs = sourceAgeMs,
            trendScorePercent = trendScore,
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

    private fun parseTrades(trades: JSONArray): List<Trade> = buildList {
        for (index in 0 until trades.length()) {
            val item = trades.optJSONObject(index) ?: continue
            val price = item.optString("price").toDoubleOrNull() ?: continue
            val amount = item.optString("amount").toDoubleOrNull() ?: 0.0
            val epochMs = toEpochMs(item.optString("date").toLongOrNull() ?: 0L)
            val type = item.optString("type").lowercase()
            if (price > 0.0) add(Trade(epochMs, price, amount, type))
        }
    }

    private fun momentumFromTrades(trades: List<Trade>): Double {
        if (trades.size < 2) return 0.0
        val timed = trades.filter { it.epochMs > 0L }.sortedBy { it.epochMs }
        val oldest = timed.firstOrNull()?.price ?: trades.last().price
        val newest = timed.lastOrNull()?.price ?: trades.first().price
        if (oldest <= 0.0) return 0.0
        return ((newest - oldest) / oldest) * 100.0
    }

    private fun tradeFlowPercent(trades: List<Trade>): Double {
        val buy = trades.filter { it.type == "buy" }.sumOf { it.amount }
        val sell = trades.filter { it.type == "sell" }.sumOf { it.amount }
        val total = buy + sell
        return if (total > 0.0) ((buy - sell) / total) * 100.0 else 0.0
    }

    private fun percentChangeFrom(history: List<Sample>, targetEpochMs: Long): Double {
        val reference = history.minByOrNull { abs(it.epochMs - targetEpochMs) } ?: return 0.0
        val latest = history.lastOrNull() ?: return 0.0
        if (reference.price <= 0.0) return 0.0
        return ((latest.price - reference.price) / reference.price) * 100.0
    }

    private fun bestPrice(levels: JSONArray?, highest: Boolean): Double? {
        if (levels == null) return null
        val prices = buildList {
            for (index in 0 until levels.length()) {
                val level = levels.optJSONObject(index)
                val value = level?.optString("price")?.toDoubleOrNull()
                    ?: levels.optJSONArray(index)?.optString(0)?.toDoubleOrNull()
                if (value != null && value > 0.0) add(value)
            }
        }
        return if (highest) prices.maxOrNull() else prices.minOrNull()
    }

    private fun standardDeviationPercent(prices: List<Double>): Double {
        val mean = prices.average()
        if (mean <= 0.0) return 0.0
        val variance = prices.sumOf { (it - mean) * (it - mean) } / prices.size
        return sqrt(variance) / mean * 100.0
    }

    private fun firstPositive(vararg values: Double?): Double = values.firstOrNull { it != null && it > 0.0 } ?: 0.0

    private fun toEpochMs(value: Long): Long = when {
        value <= 0L -> 0L
        value < 10_000_000_000L -> value * 1_000L
        else -> value
    }
}
