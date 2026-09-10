package com.mirei.app.runtime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.SharedPreferences
import android.net.ConnectivityManager
import android.net.Network
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import com.mirei.app.core.DecisionMode
import com.mirei.app.core.MireiState
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TradingConfig
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.TradeLedgerFactory
import java.util.Locale

class MireiForegroundService : Service() {
    private val controller = MireiRuntimeController()
    private var config = TradingConfig()
    private var symbol = DEFAULT_SYMBOL
    private var exchangeId = DEFAULT_EXCHANGE
    private var managedSymbols = listOf(DEFAULT_SYMBOL)
    private var sessionStarted = false
    private lateinit var workerThread: HandlerThread
    private lateinit var worker: Handler
    private lateinit var runtime: MireiPaperTradingRuntime
    private lateinit var marketData: IndodaxMarketDataSource
    private lateinit var prefs: SharedPreferences
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var internetAvailable = false
    @Volatile private var lastScannerSummary = ""
    private var lastScanEpochMs = 0L
    private var lastNotificationKey = ""

    override fun onCreate() {
        super.onCreate()
        try {
            prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            config = loadConfig()
            getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(CHANNEL_ID, "Mirei Runtime", NotificationManager.IMPORTANCE_LOW))
            workerThread = HandlerThread("mirei-runtime-worker").also { it.start() }
            worker = Handler(workerThread.looper)
            marketData = IndodaxMarketDataSource()
            createRuntime()
            val connectivity = getSystemService(ConnectivityManager::class.java)
            connectivityManager = connectivity
            internetAvailable = connectivity.activeNetwork != null
            val callback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) { internetAvailable = true; publishHealth() }
                override fun onLost(network: Network) { internetAvailable = false; controller.onNetworkLost(); publishHealth() }
            }
            networkCallback = callback
            connectivity.registerDefaultNetworkCallback(callback)
            publishHealth()
        } catch (error: Exception) {
            handleRuntimeFailure("Mirei initialization failed", error)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            startForeground(NOTIFICATION_ID, notification("${stateLabel()} · ${managedSymbols.size} market"))
            when (intent?.action) {
                ACTION_START -> startRuntime(intent)
                ACTION_HOLD -> { controller.hold(); worker.removeCallbacksAndMessages(null); publishHealth() }
                ACTION_STOP -> { controller.stop(); worker.removeCallbacksAndMessages(null); publishHealth() }
                ACTION_CLOSE_ALL -> closeAll()
                ACTION_REFRESH -> worker.post {
                    if (sessionStarted) {
                        runScanner()
                        publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)))
                    } else {
                        runScanner()
                        publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)))
                    }
                }
                ACTION_APPLY_RISK -> worker.post {
                    if (sessionStarted) {
                        applyRisk()
                        publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)))
                    } else publishHealth()
                }
                ACTION_DELETE_HISTORY -> { MireiDatabase(this).clearHistory(); publishHealth() }
            }
        } catch (error: Exception) {
            handleRuntimeFailure("Mirei action failed", error)
        }
        return START_NOT_STICKY
    }

    private fun startRuntime(intent: Intent) {
        if (sessionStarted) {
            controller.start()
            worker.removeCallbacksAndMessages(null)
            worker.post {
                runScanner()
                publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)))
                worker.post(runtimeLoop)
            }
            return
        }
        val allocations = parseAllocations(intent.getStringExtra(EXTRA_INITIAL_ALLOCATIONS).orEmpty())
        if (allocations.isEmpty()) throw IllegalArgumentException("initial_holdings_required")
        symbol = intent.getStringExtra(EXTRA_SYMBOL)?.takeIf { it in SUPPORTED_MARKETS } ?: allocations.keys.first()
        managedSymbols = allocations.keys.take(3)
        exchangeId = intent.getStringExtra(EXTRA_EXCHANGE)?.lowercase()?.takeIf { it in SUPPORTED_EXCHANGES } ?: DEFAULT_EXCHANGE
        require(exchangeId == DEFAULT_EXCHANGE) { "exchange_adapter_not_connected:$exchangeId" }
        config = loadConfig()
        createRuntime()
        controller.start()
        worker.removeCallbacksAndMessages(null)
        worker.post {
            val seeded = runtime.seedInitialHoldings(allocations, System.currentTimeMillis())
            if (seeded.size != allocations.size || seeded.any { !it.success }) {
                publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, false)))
                return@post
            }
            sessionStarted = true
            runScanner()
            lastScanEpochMs = System.currentTimeMillis()
            publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)))
            worker.post(runtimeLoop)
        }
    }

    private fun parseAllocations(raw: String): LinkedHashMap<String, Double> = linkedMapOf<String, Double>().apply {
        raw.split(';').forEach { token ->
            val parts = token.split('=')
            val amount = parts.getOrNull(1)?.toDoubleOrNull()
            val pair = parts.getOrNull(0)?.trim()
            if (pair != null && pair in SUPPORTED_MARKETS && amount != null && amount > 0.0) put(pair, amount)
        }
    }

    private fun createRuntime() {
        runtime = MireiPaperTradingRuntime(config, marketData, TradeLedgerFactory.create(this), symbol, exchangeId, managedSymbols)
    }

    private fun applyRisk() {
        config = loadConfig()
        runtime.applyRiskConfig(config)
    }

    private val runtimeLoop = object : Runnable {
        override fun run() {
            if (controller.state != MireiState.RUNNING || !sessionStarted) return
            val now = System.currentTimeMillis()
            if (now - lastScanEpochMs >= SCAN_INTERVAL_MS) {
                runScanner()
                lastScanEpochMs = now
            }
            val status = runtime.tick(now, RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE))
            publishStatus(status)
            persistDecisions(status)
            if (controller.state == MireiState.RUNNING) worker.postDelayed(this, TICK_MS)
        }
    }

    private fun persistDecisions(status: PaperRuntimeStatus) {
        val db = MireiDatabase(this)
        status.decisionsBySymbol.forEach { (pair, decision) ->
            db.recordSuggestion(pair, decision.action.name, decision.confidence, decision.rationale, status.lastTickEpochMs)
        }
        status.recentExecutions.forEach { execution ->
            val eventType = when (execution.reason) {
                "stop_loss" -> "SL_CLOSE"
                "take_profit" -> "TP_CLOSE"
                "manual_close_all" -> "MANUAL_CLOSE"
                "re_entry" -> "RE_ENTRY"
                "entry_filled" -> "OPEN"
                else -> "EXECUTION"
            }
            db.recordAudit(eventType, "${execution.reason ?: "execution"}|${execution.orderId ?: "-"}|pnl=${execution.pnlIdr}|balance=${execution.remainingBalanceIdr}", status.lastTickEpochMs)
        }
    }

    private fun closeAll() {
        val wasRunning = controller.state == MireiState.RUNNING
        controller.closeAll()
        worker.post {
            val status = runtime.closeAll(System.currentTimeMillis(), RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE))
            persistDecisions(status)
            if (wasRunning) controller.start()
            publishStatus(status)
            if (wasRunning) worker.post(runtimeLoop)
        }
    }

    private fun runScanner() {
        val results = SUPPORTED_MARKETS.mapNotNull { pair -> marketData.snapshot(pair)?.let { pair to it } }
        val totalVolume = results.sumOf { it.second.volume24h }
        val ranked = results.sortedByDescending { it.second.trendScorePercent }
        lastScannerSummary = ranked.joinToString("\n") { (pair, snapshot) ->
            val share = if (totalVolume > 0.0) snapshot.volume24h / totalVolume * 100.0 else 0.0
            listOf(pair, "%.2f".format(Locale.US, snapshot.price), "%.3f".format(Locale.US, snapshot.change1mPercent), "%.3f".format(Locale.US, snapshot.momentumPercent), "%.3f".format(Locale.US, snapshot.trendScorePercent), "%.2f".format(Locale.US, share)).joinToString("|")
        }
        runtime.updateScannerSummary(lastScannerSummary)
    }

    override fun onDestroy() {
        try { networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) } } catch (_: Exception) { }
        if (::workerThread.isInitialized) workerThread.quitSafely()
        networkCallback = null
        connectivityManager = null
        super.onDestroy()
    }

    private fun handleRuntimeFailure(message: String, error: Throwable) {
        controller.onEngineError()
        runCatching { publish("ERROR · $message · ${error.javaClass.simpleName}", force = true) }
        runCatching { publishHealth() }
    }

    private fun publishStatus(status: PaperRuntimeStatus) {
        val intent = Intent(ACTION_STATUS).setPackage(packageName).apply {
            putExtra(EXTRA_STATE, controller.state.name)
            putExtra(EXTRA_SYMBOL, status.marketSymbol)
            putExtra(EXTRA_EXCHANGE, exchangeId)
            putExtra(EXTRA_PRICE, status.marketPrice)
            putExtra(EXTRA_BID, status.marketBidPrice)
            putExtra(EXTRA_ASK, status.marketAskPrice)
            putExtra(EXTRA_HIGH_24H, status.marketHigh24h)
            putExtra(EXTRA_LOW_24H, status.marketLow24h)
            putExtra(EXTRA_VOLUME_24H, status.marketVolume24h)
            putExtra(EXTRA_EQUITY, status.equityIdr)
            putExtra(EXTRA_BALANCE, status.availableBalanceIdr)
            putExtra(EXTRA_PNL, status.dailyPnlIdr)
            putExtra(EXTRA_POSITIONS, status.activePositions.size)
            putExtra(EXTRA_CONFIDENCE, status.lastDecision?.confidence ?: 0.0)
            putExtra(EXTRA_ACTION, status.lastDecision?.action?.name ?: "HOLD")
            putExtra(EXTRA_RATIONALE, status.lastDecision?.rationale ?: "no_decision")
            putExtra(EXTRA_AGENT_SUMMARY, status.decisionsBySymbol.entries.joinToString("\n\n") { (pair, decision) -> "$pair => " + decision.observations.joinToString(" | ") { observation -> "${observation.agent.name}:${observation.action.name} ${(observation.confidence * 100).toInt()}% ${observation.rationale}" } })
            putExtra(EXTRA_ENTRY_REASONS, status.entryPlanReasons.joinToString(" | "))
            putExtra(EXTRA_MOMENTUM, status.marketMomentumPercent)
            putExtra(EXTRA_VOLATILITY, status.marketVolatilityPercent)
            putExtra(EXTRA_SENTIMENT, status.marketSentimentScore)
            putExtra(EXTRA_FORECAST_CONFIDENCE, status.forecastConfidence)
            putExtra(EXTRA_SPREAD, status.marketSpreadPercent)
            putExtra(EXTRA_CHANGE_TICK, status.changeSinceLastTickPercent)
            putExtra(EXTRA_CHANGE_1M, status.change1mPercent)
            putExtra(EXTRA_CHANGE_5M, status.change5mPercent)
            putExtra(EXTRA_CHANGE_15M, status.change15mPercent)
            putExtra(EXTRA_FLOW, status.tradeFlowPercent)
            putExtra(EXTRA_TREND, status.trendScorePercent)
            putExtra(EXTRA_TRADE_COUNT, status.tradeCount)
            putExtra(EXTRA_BUY_VOLUME, status.buyVolume)
            putExtra(EXTRA_SELL_VOLUME, status.sellVolume)
            putExtra(EXTRA_LAST_TRADE, status.lastTradeEpochMs)
            putExtra(EXTRA_SNAPSHOT_TIME, status.snapshotEpochMs)
            putExtra(EXTRA_SOURCE_AGE, status.sourceAgeMs)
            putExtra(EXTRA_MARKET_FRESH, status.marketDataFresh)
            putExtra(EXTRA_INTERNET, status.internetAvailable)
            putExtra(EXTRA_EXCHANGE_HEALTHY, status.exchangeHealthy)
            putExtra(EXTRA_ERROR, status.lastError)
            putExtra(EXTRA_RECENT_EXECUTIONS, status.recentExecutions.joinToString("\n") { execution -> "${execution.reason ?: "execution"} | PnL Rp ${"%.2f".format(Locale.US, execution.pnlIdr)} | Kas Rp ${"%.2f".format(Locale.US, execution.remainingBalanceIdr)} | ${execution.orderId ?: "-"}" })
            putExtra(EXTRA_POSITIONS_DETAIL, status.activePositions.joinToString("\n") { p ->
                val snapshot = status.snapshotsBySymbol[p.symbol]
                val current = snapshot?.price ?: p.entryPrice
                val amount = p.stakeIdr / p.entryPrice
                val value = current * amount
                val unrealized = value - p.stakeIdr
                val tpDistance = (p.takeProfitPrice / p.entryPrice - 1.0) * 100.0
                val slDistance = (1.0 - p.stopLossPrice / p.entryPrice) * 100.0
                "${p.symbol}|stake=${"%.2f".format(Locale.US, p.stakeIdr)}|entry=${"%.2f".format(Locale.US, p.entryPrice)}|current=${"%.2f".format(Locale.US, current)}|value=${"%.2f".format(Locale.US, value)}|unrealized=${"%.2f".format(Locale.US, unrealized)}|tp=${"%.2f".format(Locale.US, p.takeProfitPrice)}|sl=${"%.2f".format(Locale.US, p.stopLossPrice)}|tp_pct=${"%.3f".format(Locale.US, tpDistance)}|sl_pct=${"%.3f".format(Locale.US, slDistance)}|entry_reason=${p.entryReason}"
            })
            putExtra(EXTRA_SCANNER, status.scannerSummary)
            putExtra(EXTRA_TICK, status.lastTickEpochMs)
        }
        sendBroadcast(intent)

        val meaningfulEvent = when {
            !status.lastError.isNullOrBlank() -> "ERROR:${status.lastError}"
            status.recentExecutions.isNotEmpty() -> status.recentExecutions.last().let { execution -> "EXEC:${execution.orderId}:${execution.reason}:${execution.pnlIdr}:${status.lastTickEpochMs}" }
            else -> "STATE:${controller.state.name}"
        }
        publish(meaningfulEvent, force = false)
    }

    private fun publishHealth() = publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)))

    private fun publish(text: String, force: Boolean) {
        val key = if (force) "force:${System.currentTimeMillis()}" else text
        if (!force && key == lastNotificationKey) return
        if (!force && text.startsWith("STATE:HOLD")) return
        lastNotificationKey = key
        val visible = when {
            text.startsWith("EXEC:") -> text.removePrefix("EXEC:").replace(':', '·')
            text.startsWith("ERROR:") -> text.removePrefix("ERROR:").replace('_', ' ')
            text.startsWith("STATE:") -> text.removePrefix("STATE:")
            else -> text
        }
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(visible))
    }

    private fun notification(text: String): Notification = Notification.Builder(this, CHANNEL_ID)
        .setContentTitle("Mirei · Paper Trading")
        .setContentText(text)
        .setStyle(Notification.BigTextStyle().bigText(text))
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setOngoing(true)
        .build()

    private fun stateLabel(): String = when (controller.state) {
        MireiState.RUNNING -> "BERJALAN"
        MireiState.HOLD -> "HOLD"
        MireiState.STOP -> "BERHENTI"
        else -> controller.state.name
    }

    private fun loadConfig(): TradingConfig {
        val mode = runCatching { ScalpingMode.valueOf(prefs.getString(KEY_MODE, ScalpingMode.BALANCED.name)!!) }.getOrDefault(ScalpingMode.BALANCED)
        val manual = prefs.getBoolean(KEY_MANUAL, false)
        val sl = prefs.getString(KEY_MANUAL_SL, null)?.toDoubleOrNull()
        val tp = prefs.getString(KEY_MANUAL_TP, null)?.toDoubleOrNull()
        return if (manual && sl != null && tp != null && tp > sl) {
            TradingConfig(mode = mode, decisionMode = DecisionMode.SUGGESTION, manualRiskMode = com.mirei.app.core.ManualRiskMode.MANUAL, manualStopLossPercent = sl, manualTakeProfitPercent = tp)
        } else {
            TradingConfig(mode = mode, decisionMode = DecisionMode.SUGGESTION)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_START = "com.mirei.app.action.START"
        const val ACTION_HOLD = "com.mirei.app.action.HOLD"
        const val ACTION_STOP = "com.mirei.app.action.STOP"
        const val ACTION_CLOSE_ALL = "com.mirei.app.action.CLOSE_ALL"
        const val ACTION_REFRESH = "com.mirei.app.action.REFRESH"
        const val ACTION_APPLY_RISK = "com.mirei.app.action.APPLY_RISK"
        const val ACTION_DELETE_HISTORY = "com.mirei.app.action.DELETE_HISTORY"
        const val ACTION_STATUS = "com.mirei.app.action.STATUS"
        const val EXTRA_STATE = "state"
        const val EXTRA_SYMBOL = "symbol"
        const val EXTRA_EXCHANGE = "exchange"
        const val EXTRA_INITIAL_ALLOCATIONS = "initial_allocations"
        const val EXTRA_PRICE = "price"
        const val EXTRA_BID = "bid"
        const val EXTRA_ASK = "ask"
        const val EXTRA_HIGH_24H = "high_24h"
        const val EXTRA_LOW_24H = "low_24h"
        const val EXTRA_VOLUME_24H = "volume_24h"
        const val EXTRA_EQUITY = "equity"
        const val EXTRA_BALANCE = "balance"
        const val EXTRA_PNL = "daily_pnl"
        const val EXTRA_POSITIONS = "positions"
        const val EXTRA_CONFIDENCE = "confidence"
        const val EXTRA_ACTION = "action"
        const val EXTRA_RATIONALE = "rationale"
        const val EXTRA_AGENT_SUMMARY = "agent_summary"
        const val EXTRA_ENTRY_REASONS = "entry_reasons"
        const val EXTRA_MOMENTUM = "momentum"
        const val EXTRA_VOLATILITY = "volatility"
        const val EXTRA_SENTIMENT = "sentiment"
        const val EXTRA_FORECAST_CONFIDENCE = "forecast_confidence"
        const val EXTRA_SPREAD = "spread"
        const val EXTRA_CHANGE_TICK = "change_tick"
        const val EXTRA_CHANGE_1M = "change_1m"
        const val EXTRA_CHANGE_5M = "change_5m"
        const val EXTRA_CHANGE_15M = "change_15m"
        const val EXTRA_FLOW = "trade_flow"
        const val EXTRA_TREND = "trend"
        const val EXTRA_TRADE_COUNT = "trade_count"
        const val EXTRA_BUY_VOLUME = "buy_volume"
        const val EXTRA_SELL_VOLUME = "sell_volume"
        const val EXTRA_LAST_TRADE = "last_trade"
        const val EXTRA_SNAPSHOT_TIME = "snapshot_time"
        const val EXTRA_SOURCE_AGE = "source_age"
        const val EXTRA_MARKET_FRESH = "market_fresh"
        const val EXTRA_INTERNET = "internet"
        const val EXTRA_EXCHANGE_HEALTHY = "exchange_healthy"
        const val EXTRA_ERROR = "error"
        const val EXTRA_RECENT_EXECUTIONS = "recent_executions"
        const val EXTRA_POSITIONS_DETAIL = "positions_detail"
        const val EXTRA_SCANNER = "scanner"
        const val EXTRA_TICK = "tick"
        const val DEFAULT_SYMBOL = "BTC/IDR"
        const val DEFAULT_EXCHANGE = "indodax"
        val SUPPORTED_MARKETS = listOf("BTC/IDR", "ETH/IDR", "HYPE/IDR", "FARTCOIN/IDR", "SOL/IDR", "XRP/IDR", "DOGE/IDR", "ADA/IDR", "SUI/IDR", "TRX/IDR")
        val SUPPORTED_EXCHANGES = listOf("indodax", "binance", "bingx", "bitget", "bybit", "gate", "htx", "hyperliquid", "kraken", "okx")
        private const val CHANNEL_ID = "mirei_runtime"
        private const val NOTIFICATION_ID = 1001
        private const val TICK_MS = 5_000L
        private const val SCAN_INTERVAL_MS = 60_000L
        private const val PREFS_NAME = "mirei_settings"
        private const val KEY_MODE = "mode"
        private const val KEY_MANUAL = "manual_risk"
        private const val KEY_MANUAL_SL = "manual_sl"
        private const val KEY_MANUAL_TP = "manual_tp"
    }
}
