package com.mirei.app.runtime

import com.mirei.app.core.AssetClass
import com.mirei.app.core.MarketInstrument
import com.mirei.app.core.MarketSnapshot
import com.mirei.app.core.TradingUniverse
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Routes market data by MarketInstrument.providerId. Indodax remains the native
 * crypto source; Yahoo Finance is a public delayed-data source for paper-only
 * stock/forex/commodity observation. It is not represented as live broker access.
 */
class MultiMarketDataSource(
    private val indodax: IndodaxMarketDataSource = IndodaxMarketDataSource(),
    private val timeoutMs: Int = 3_000,
) : PaperMarketDataSource {
    private val yahooCache = mutableMapOf<String, CachedYahoo>()
    private var usdIdrCache: CachedRate? = null

    override fun snapshot(symbol: String): MarketSnapshot? {
        val instrument = TradingUniverse.bySymbol(symbol) ?: return null
        return when (instrument.providerId) {
            "indodax" -> indodax.snapshot(symbol)
            "yahoo_finance" -> yahooSnapshot(instrument)
            else -> null
        }
    }

    private fun yahooSnapshot(instrument: MarketInstrument): MarketSnapshot? {
        val now = System.currentTimeMillis()
        val raw = yahooChart(instrument.providerSymbol) ?: return null
        val closes = raw.closes
        if (closes.isEmpty()) return null
        val latest = closes.lastOrNull() ?: return null
        val usdIdr = if (instrument.quoteCurrency == "USD") usdIdr() else 1.0
        val price = latest * usdIdr
        if (price <= 0.0) return null
        val first1m = closes.firstOrNull { raw.timestamps.getOrNull(closes.indexOf(it)) ?: 0L >= now - 60_000L }
        val change1m = percentChange(first1m ?: closes.getOrNull((closes.size - 2).coerceAtLeast(0)), latest)
        val change5m = percentChange(closes.getOrNull((closes.size - 6).coerceAtLeast(0)), latest)
        val change15m = percentChange(closes.getOrNull((closes.size - 16).coerceAtLeast(0)), latest)
        val momentum = (change1m * 0.70 + change5m * 0.30)
        val volatility = if (closes.size >= 2) standardDeviationPercent(closes.takeLast(30)) else 0.01
        val trend = (momentum * 20.0 + change5m * 8.0).coerceIn(-100.0, 100.0)
        val sentiment = (change5m * 6.0 + change1m * 10.0).coerceIn(-100.0, 100.0)
        val confidence = (0.50 + abs(trend) / 200.0).coerceIn(0.50, 0.95)
        val rawBid = raw.bid ?: latest
        val rawAsk = raw.ask ?: latest
        val bid = rawBid * usdIdr
        val ask = rawAsk * usdIdr
        val spread = if (ask >= bid && bid > 0.0) ((ask - bid) / ((ask + bid) / 2.0)) * 100.0 else instrument.executionCosts.spreadPercent
        val lastEpoch = raw.timestamps.lastOrNull() ?: now
        val sourceAge = (now - lastEpoch).coerceAtLeast(0L)
        val fresh = sourceAge <= 120_000L
        val scale = usdIdr
        return MarketSnapshot(
            symbol = instrument.symbol,
            price = price,
            momentumPercent = momentum,
            volatilityPercent = volatility.coerceAtLeast(0.01),
            sentimentScore = sentiment,
            forecastConfidence = confidence,
            dataFresh = fresh,
            bidPrice = bid,
            askPrice = ask,
            high24h = (raw.high ?: latest) * scale,
            low24h = (raw.low ?: latest) * scale,
            volume24h = raw.volume,
            spreadPercent = spread,
            changeSinceLastTickPercent = change1m,
            change1mPercent = change1m,
            change5mPercent = change5m,
            change15mPercent = change15m,
            tradeFlowPercent = 0.0,
            trendScorePercent = trend,
            tradeCount = closes.size,
            buyVolume = 0.0,
            sellVolume = 0.0,
            lastTradeEpochMs = lastEpoch,
            snapshotEpochMs = now,
            sourceAgeMs = sourceAge,
            assetClass = instrument.assetClass,
            providerId = instrument.providerId,
            quoteCurrency = instrument.quoteCurrency,
        )
    }

    private fun usdIdr(): Double {
        val now = System.currentTimeMillis()
        usdIdrCache?.takeIf { now - it.atMs < 30_000L }?.let { return it.rate }
        val chart = yahooChart("USDIDR=X")
        val rate = chart?.closes?.lastOrNull()?.takeIf { it > 0.0 } ?: 17_500.0
        usdIdrCache = CachedRate(rate, now)
        return rate
    }

    private data class CachedRate(val rate: Double, val atMs: Long)
    private data class CachedYahoo(val atMs: Long, val value: YahooData)
    private data class YahooData(
        val timestamps: List<Long>,
        val closes: List<Double>,
        val high: Double?,
        val low: Double?,
        val volume: Double,
        val bid: Double?,
        val ask: Double?,
    )

    private fun yahooChart(symbol: String): YahooData? {
        val now = System.currentTimeMillis()
        yahooCache[symbol]?.takeIf { now - it.atMs < 8_000L }?.let { return it.value }
        val encoded = symbol.replace("=", "%3D")
        val url = "https://query1.finance.yahoo.com/v8/finance/chart/$encoded?range=1d&interval=1m&includePrePost=false"
        val json = runCatching { JSONObject(get(url)) }.getOrNull() ?: return null
        val result = json.optJSONObject("chart")?.optJSONArray("result")?.optJSONObject(0) ?: return null
        val meta = result.optJSONObject("meta") ?: JSONObject()
        val timestamps = buildList {
            val array = result.optJSONArray("timestamp")
            if (array != null) for (i in 0 until array.length()) add(array.optLong(i) * 1000L)
        }
        val quote = result.optJSONObject("indicators")?.optJSONArray("quote")?.optJSONObject(0) ?: return null
        val closeArray = quote.optJSONArray("close") ?: return null
        val closes = buildList {
            for (i in 0 until closeArray.length()) closeArray.optDouble(i, Double.NaN).takeIf { it.isFinite() && it > 0.0 }?.let { add(it) }
        }
        if (closes.isEmpty()) return null
        val high = meta.optDouble("regularMarketDayHigh", Double.NaN).takeIf { it.isFinite() && it > 0.0 }
        val low = meta.optDouble("regularMarketDayLow", Double.NaN).takeIf { it.isFinite() && it > 0.0 }
        val volume = meta.optDouble("regularMarketVolume", 0.0).coerceAtLeast(0.0)
        val bid = meta.optDouble("bid", Double.NaN).takeIf { it.isFinite() && it > 0.0 }
        val ask = meta.optDouble("ask", Double.NaN).takeIf { it.isFinite() && it > 0.0 }
        val data = YahooData(timestamps, closes, high, low, volume, bid, ask)
        yahooCache[symbol] = CachedYahoo(now, data)
        return data
    }

    private fun get(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = timeoutMs
        connection.readTimeout = timeoutMs
        connection.requestMethod = "GET"
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("User-Agent", "Mirei-Paper/1.0")
        return try {
            if (connection.responseCode !in 200..299) throw IllegalStateException("market_http_${connection.responseCode}")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun percentChange(old: Double?, latest: Double): Double {
        if (old == null || old <= 0.0) return 0.0
        return ((latest - old) / old) * 100.0
    }

    private fun standardDeviationPercent(values: List<Double>): Double {
        val clean = values.filter { it > 0.0 }
        if (clean.size < 2) return 0.01
        val mean = clean.average()
        if (mean <= 0.0) return 0.01
        val variance = clean.sumOf { (it - mean) * (it - mean) } / clean.size
        return sqrt(variance) / mean * 100.0
    }
}
