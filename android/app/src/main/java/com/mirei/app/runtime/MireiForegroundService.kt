package com.mirei.app.runtime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.mirei.app.core.DecisionMode
import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TradingConfig
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.PaperSessionSnapshot
import com.mirei.app.storage.PaperSessionStore
import java.util.Locale

class MireiForegroundService : Service() {
    private lateinit var workerThread: HandlerThread
    private lateinit var worker: Handler
    private lateinit var sessionStore: PaperSessionStore
    private lateinit var prefs: android.content.SharedPreferences
    private lateinit var connectivityManager: ConnectivityManager
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private lateinit var runtime: MireiPaperTradingRuntime
    private var marketData: IndodaxMarketDataSource = IndodaxMarketDataSource()
    private var controller = MireiRuntimeController()
    private var config = TradingConfig()
    private var internetAvailable = false
    private var sessionStarted = false
    private var sessionCreatedAtEpochMs = 0L
    private var runStartedAtEpochMs = 0L
    private var runStoppedAtEpochMs = 0L
    private var timestampResetAtEpochMs = 0L
    private var symbol = DEFAULT_SYMBOL
    private var exchangeId = DEFAULT_EXCHANGE
    private var managedSymbols = listOf(DEFAULT_SYMBOL)
    private var lastScanEpochMs = 0L
    private var lastNotificationKey = ""
    private var lastScannerSummary = ""

    override fun onCreate() {
        super.onCreate()
        try {
            sessionStore = PaperSessionStore(this)
            prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            config = loadConfig()
            getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(CHANNEL_ID, "Mirei Runtime", NotificationManager.IMPORTANCE_LOW))
            workerThread = HandlerThread("mirei-runtime-worker").also { it.start() }
            worker = Handler(workerThread.looper)
            marketData = IndodaxMarketDataSource()
            val saved = sessionStore.load()
            if (saved != null && saved.active) restoreSessionMetadata(saved)
            createRuntime()
            if (saved != null && saved.active) restoreRuntimeState(saved)
            val connectivity = getSystemService(ConnectivityManager::class.java)
            connectivityManager = connectivity
            internetAvailable = connectivity.activeNetwork != null
            val callback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    internetAvailable = true
                    publishHealth()
                }
                override fun onLost(network: Network) {
                    internetAvailable = false
                    controller.onNetworkLost()
                    publishHealth()
                }
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
                ACTION_HOLD -> pauseRuntime("HOLD")
                ACTION_STOP -> stopRuntime()
                ACTION_CLOSE_ALL -> closeAll()
                ACTION_TOP_UP -> worker.post { topUp(intent.getDoubleExtra(EXTRA_TOP_UP_AMOUNT, 0.0)) }
                ACTION_HUMAN_VERIFY -> worker.post { humanVerify(intent) }
                ACTION_REFRESH -> worker.post { runCatching { runScanner() }; publishHealth() }
                ACTION_APPLY_RISK -> worker.post { runCatching { if (sessionStarted) applyRisk() }; publishHealth() }
                ACTION_DELETE_HISTORY -> { runCatching { MireiDatabase(this).clearHistory() }; publishHealth() }
                ACTION_RESET_SESSION -> resetSession()
                ACTION_RESET_CLOCK -> resetClock()
            }
        } catch (error: Exception) {
            handleRuntimeFailure("Mirei action failed", error)
        }
        return START_NOT_STICKY
    }

    private fun startRuntime(intent: Intent) {
        if (sessionStarted) {
            if (!internetAvailable) {
                controller.hold()
                lastNotificationKey = "SEARCHING:${System.currentTimeMillis()}"
                publishHealth()
                return
            }
            worker.removeCallbacksAndMessages(null)
            worker.post {
                runCatching {
                    sessionStore.load()?.takeIf { it.active }?.let { saved ->
                        restoreSessionMetadata(saved)
                        restoreRuntimeState(saved)
                    }
                    controller.start()
                    val now = System.currentTimeMillis()
                    runStartedAtEpochMs = now
                    runStoppedAtEpochMs = 0L
                    runScanner()
                    lastScanEpochMs = now
                    persistSession()
                    publishHealth()
                    val status = runtime.tick(now, RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE))
                    publishStatus(status)
                    persistDecisions(status)
                    persistSession()
                    worker.postDelayed(runtimeLoop, TICK_MS)
                }.onFailure { error -> handleRuntimeFailure("Mirei restart failed", error) }
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
        require(allocations.values.sum() <= config.totalCapitalIdr + 1e-6) { "allocation_exceeds_session_capital" }
        createRuntime()
        controller.start()
        worker.removeCallbacksAndMessages(null)
        worker.post {
            runCatching {
                val seeded = runtime.seedInitialHoldings(allocations, System.currentTimeMillis())
                if (seeded.size != allocations.size || seeded.any { !it.success }) {
                    controller.stop()
                    publishHealth()
                    return@runCatching
                }
                val now = System.currentTimeMillis()
                sessionStarted = true
                sessionCreatedAtEpochMs = now
                runStartedAtEpochMs = now
                runStoppedAtEpochMs = 0L
                timestampResetAtEpochMs = 0L
                runScanner()
                lastScanEpochMs = now
                persistSession()
                publishHealth()
                worker.post(runtimeLoop)
            }.onFailure { error -> handleRuntimeFailure("Mirei start failed", error) }
        }
    }

    private fun restoreSessionMetadata(saved: PaperSessionSnapshot) {
        sessionStarted = true
        sessionCreatedAtEpochMs = saved.sessionCreatedAtEpochMs
        runStartedAtEpochMs = saved.runStartedAtEpochMs
        runStoppedAtEpochMs = saved.runStoppedAtEpochMs
        timestampResetAtEpochMs = saved.timestampResetAtEpochMs
        symbol = saved.symbol.ifBlank { DEFAULT_SYMBOL }
        exchangeId = saved.exchangeId.ifBlank { DEFAULT_EXCHANGE }
        managedSymbols = saved.managedSymbols.ifEmpty { listOf(symbol) }.take(3)
    }

    private fun restoreRuntimeState(saved: PaperSessionSnapshot) {
        runtime.restoreState(PaperRuntimePersistence(
            engineState = PaperEngineState(saved.availableBalanceIdr, saved.positions),
            dailyPnlIdr = saved.dailyPnlIdr,
            consecutiveLosses = saved.consecutiveLosses,
            holdingsSeeded = saved.holdingsSeeded,
            buyDecisionCount = saved.buyDecisionCount,
            holdDecisionCount = saved.holdDecisionCount,
            sellDecisionCount = saved.sellDecisionCount,
            initialCapitalBySymbol = saved.initialCapitalBySymbol,
        ))
    }

    private fun pauseRuntime(reason: String) {
        controller.hold()
        worker.removeCallbacksAndMessages(null)
        runStoppedAtEpochMs = System.currentTimeMillis()
        persistSession()
        runCatching { MireiDatabase(this).recordAudit("SESSION_PAUSED", reason, runStoppedAtEpochMs) }
        publishHealth()
    }

    private fun stopRuntime() {
        controller.stop()
        worker.removeCallbacksAndMessages(null)
        runStoppedAtEpochMs = System.currentTimeMillis()
        persistSession()
        runCatching { MireiDatabase(this).recordAudit("SESSION_STOPPED", "runtime_paused", runStoppedAtEpochMs) }
        publishHealth()
    }

    private fun resetSession() {
        controller.stop()
        worker.removeCallbacksAndMessages(null)
        sessionStarted = false
        sessionCreatedAtEpochMs = 0L
        runStartedAtEpochMs = 0L
        runStoppedAtEpochMs = System.currentTimeMillis()
        timestampResetAtEpochMs = 0L
        sessionStore.clearSession()
        config = loadConfig()
        createRuntime()
        runCatching { MireiDatabase(this).recordAudit("SESSION_RESET", "portfolio_session_reset_without_history_delete") }
        publishHealth()
    }

    private fun resetClock() {
        val now = System.currentTimeMillis()
        timestampResetAtEpochMs = now
        if (controller.state == MireiState.RUNNING) runStartedAtEpochMs = now else runStoppedAtEpochMs = now
        persistSession()
        publishHealth()
    }

    private fun topUp(amountIdr: Double) {
        if (!sessionStarted) {
            runCatching { MireiDatabase(this).recordAudit("TOP_UP_REJECTED", "no_active_session") }
            publishHealth()
            return
        }
        val before = runtime.status().availableBalanceIdr
        val status = runtime.topUp(amountIdr)
        if (status.lastExecution?.reason == "top_up") {
            val newCapital = (prefs.getString(KEY_TOTAL_CAPITAL, null)?.toDoubleOrNull() ?: config.totalCapitalIdr) + amountIdr
            prefs.edit().putString(KEY_TOTAL_CAPITAL, newCapital.toString()).apply()
            runCatching { MireiDatabase(this).recordAudit("TOP_UP", "amount=$amountIdr|balance_before=$before|balance_after=${status.availableBalanceIdr}") }
        } else {
            runCatching { MireiDatabase(this).recordAudit("TOP_UP_REJECTED", "amount=$amountIdr|reason=${status.lastError ?: "invalid_top_up"}") }
        }
        persistSession()
        publishStatus(status)
    }

    private fun humanVerify(intent: Intent) {
        if (!sessionStarted || controller.state != MireiState.RUNNING) { publishHealth(); return }
        val requestedSymbol = intent.getStringExtra(EXTRA_HUMAN_SYMBOL)?.takeIf { it in managedSymbols } ?: symbol
        val confirmed = intent.getStringExtra(EXTRA_HUMAN_AGENTS).orEmpty().split(',').map { it.trim() }.filter { it.isNotBlank() }.toSet()
        val status = runtime.confirmHumanBuy(requestedSymbol, confirmed, System.currentTimeMillis())
        persistDecisions(status)
        persistSession()
        runCatching { if (status.recentExecutions.isNotEmpty()) MireiDatabase(this).recordAudit("HUMAN_VERIFIED_ENTRY", "symbol=$requestedSymbol|agents=${confirmed.joinToString(",")}", status.lastTickEpochMs) }
        publishStatus(status)
    }

    private fun parseAllocations(raw: String): LinkedHashMap<String, Double> = linkedMapOf<String, Double>().apply {
        raw.split(';').forEach { token ->
            val parts = token.split('=')
            val amount = parts.getOrNull(1)?.toDoubleOrNull()
            val pair = parts.getOrNull(0)?.trim()
            if (pair != null && pair in SUPPORTED_MARKETS && amount != null && amount > 0.0) put(pair, amount)
        }
    }

    private fun createRuntime() { runtime = MireiPaperTradingRuntime(config, marketData, TradeLedgerFactory.create(this), symbol, exchangeId, managedSymbols) }

    private fun applyRisk() {
        val stored = loadConfig()
        config = stored.copy(totalCapitalIdr = config.totalCapitalIdr, positionSizeIdr = config.positionSizeIdr, maxOpenPositions = config.maxOpenPositions)
        runtime.applyRiskConfig(config)
        persistSession()
    }

    private val runtimeLoop = object : Runnable {
        override fun run() {
            if (controller.state != MireiState.RUNNING || !sessionStarted) return
            try {
                val now = System.currentTimeMillis()
                if (now - lastScanEpochMs >= SCAN_INTERVAL_MS) { runScanner(); lastScanEpochMs = now }
                val status = runtime.tick(now, RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE))
                publishStatus(status)
                persistDecisions(status)
                persistSession()
            } catch (error: Exception) {
                handleRuntimeFailure("Mirei runtime loop failed", error)
            } finally {
                if (controller.state == MireiState.RUNNING && sessionStarted) worker.postDelayed(this, TICK_MS)
            }
        }
    }

    private fun persistSession() {
        if (!sessionStarted) return
        val state = runtime.persistenceState()
        sessionStore.save(PaperSessionSnapshot(
            active = true,
            sessionCreatedAtEpochMs = sessionCreatedAtEpochMs,
            runStartedAtEpochMs = runStartedAtEpochMs,
            runStoppedAtEpochMs = runStoppedAtEpochMs,
            timestampResetAtEpochMs = timestampResetAtEpochMs,
            symbol = symbol,
            exchangeId = exchangeId,
            managedSymbols = managedSymbols,
            availableBalanceIdr = state.engineState.availableBalanceIdr,
            dailyPnlIdr = state.dailyPnlIdr,
            consecutiveLosses = state.consecutiveLosses,
            holdingsSeeded = state.holdingsSeeded,
            positions = state.engineState.positions,
            buyDecisionCount = state.buyDecisionCount,
            holdDecisionCount = state.holdDecisionCount,
            sellDecisionCount = state.sellDecisionCount,
            initialCapitalBySymbol = state.initialCapitalBySymbol,
        ))
    }

    private fun persistDecisions(status: PaperRuntimeStatus) {
        runCatching {
            val db = MireiDatabase(this)
            status.decisionsBySymbol.forEach { (pair, decision) -> db.recordSuggestion(pair, decision.action.name, decision.confidence, decision.rationale, status.lastTickEpochMs) }
            status.recentExecutions.forEach { execution ->
                val eventType = when (execution.reason) {
                    "stop_loss" -> "SL_CLOSE"
                    "take_profit" -> "TP_CLOSE"
                    "manual_close_all" -> "MANUAL_CLOSE"
                    "re_entry", "human_verified_re_entry" -> "RE_ENTRY"
                    "entry_filled", "human_verified_entry", "initial_holding_seeded" -> "OPEN"
                    "top_up" -> "TOP_UP"
                    else -> "EXECUTION"
                }
                db.recordAudit(eventType, "${execution.reason ?: "execution"}|${execution.orderId ?: "-"}|pnl=${execution.pnlIdr}|balance_before=${execution.balanceBeforeIdr}|balance_after=${execution.remainingBalanceIdr}", status.lastTickEpochMs)
            }
        }
    }

    private fun closeAll() {
        worker.post {
            val status = runCatching { runtime.closeAll(System.currentTimeMillis(), RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE)) }.getOrElse {
                handleRuntimeFailure("Mirei close all failed", it)
                runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE))
            }
            persistDecisions(status)
            if (status.activePositions.isEmpty()) {
                controller.stop()
                runStoppedAtEpochMs = System.currentTimeMillis()
                persistSession()
                runCatching { MireiDatabase(this).recordAudit("SESSION_CLOSED", "all_positions_closed", runStoppedAtEpochMs) }
            } else {
                // Do not stop a session while positions remain open. A blocked
                // close-all must preserve the running session so the user can
                // retry when market/exchange data becomes available.
                runCatching { MireiDatabase(this).recordAudit("CLOSE_ALL_BLOCKED", "positions_remaining=${status.activePositions.size}") }
                persistSession()
            }
            publishStatus(status)
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
        runCatching { persistSession() }
        runCatching { networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) } }
        if (::workerThread.isInitialized) workerThread.quitSafely()
        networkCallback = null
        connectivityManager = null
        super.onDestroy()
    }

    private fun handleRuntimeFailure(message: String, error: Throwable) {
        controller.onEngineError()
        runCatching { MireiDatabase(this).recordAudit("RUNTIME_ERROR", "$message|${error.javaClass.simpleName}|${error.message ?: ""}") }
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
            putExtra(EXTRA_ERROR, status.lastError.orEmpty())
            putExtra(EXTRA_RECENT_EXECUTIONS, status.recentExecutions.joinToString("\n") { "${it.reason} ${it.symbol} qty=${it.quantity} pnl=${"%.2f".format(Locale.US, it.pnlIdr)}" })
            putExtra(EXTRA_POSITIONS_DETAIL, status.activePositions.joinToString("\n") { "${it.symbol} entry=${it.entryPrice} sl=${it.stopLossPrice} tp=${it.takeProfitPrice}" })
            putExtra(EXTRA_SCANNER, status.scannerSummary)
            putExtra(EXTRA_TICK, status.lastTickEpochMs)
            putExtra(EXTRA_BUY_COUNT, status.buyDecisionCount)
            putExtra(EXTRA_HOLD_COUNT, status.holdDecisionCount)
            putExtra(EXTRA_SELL_COUNT, status.sellDecisionCount)
            putExtra(EXTRA_HUMAN_REQUIRED, status.humanVerificationRequired)
            putExtra(EXTRA_HUMAN_ALLOWED, status.humanAllowedIndicators.joinToString(","))
            putExtra(EXTRA_HUMAN_BLOCKED, status.humanBlockedIndicators.joinToString(","))
            putExtra(EXTRA_SESSION_CREATED, sessionCreatedAtEpochMs)
            putExtra(EXTRA_RUN_STARTED, runStartedAtEpochMs)
            putExtra(EXTRA_RUN_STOPPED, runStoppedAtEpochMs)
            putExtra(EXTRA_CLOCK_RESET, timestampResetAtEpochMs)
            putExtra(EXTRA_RISK_BASIS, config.riskReferenceMode.name)
            putExtra(EXTRA_TOTAL_CAPITAL, config.totalCapitalIdr)
        }
        sendBroadcast(intent)
        publish("${stateLabel()} · ${status.marketSymbol.ifBlank { symbol }} · ${status.activePositions.size} posisi", force = false)
    }

    private fun publishHealth() {
        val status = runtime.status(RuntimeEnvironment(internetAvailable, exchangeId == DEFAULT_EXCHANGE))
        publishStatus(status)
    }

    private fun publish(text: String, force: Boolean) {
        if (!force && text == lastNotificationKey) return
        lastNotificationKey = text
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification = NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle("Mirei ミレイ")
        .setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text))
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
        val totalCapital = prefs.getString(KEY_TOTAL_CAPITAL, null)?.toDoubleOrNull()?.takeIf { it > 0.0 } ?: 150_000.0
        val mode = runCatching { ScalpingMode.valueOf(prefs.getString(KEY_MODE, ScalpingMode.BALANCED.name)!!) }.getOrDefault(ScalpingMode.BALANCED)
        val manual = prefs.getBoolean(KEY_MANUAL, false)
        val sl = prefs.getString(KEY_MANUAL_SL, null)?.toDoubleOrNull()
        val tp = prefs.getString(KEY_MANUAL_TP, null)?.toDoubleOrNull()
        val referenceMode = runCatching { RiskReferenceMode.valueOf(prefs.getString(KEY_RISK_BASIS, RiskReferenceMode.ENTRY_PRICE.name)!!) }.getOrDefault(RiskReferenceMode.ENTRY_PRICE)
        return if (manual && sl != null && tp != null && tp > sl) {
            TradingConfig(totalCapitalIdr = totalCapital, mode = mode, decisionMode = DecisionMode.SUGGESTION, manualRiskMode = ManualRiskMode.MANUAL, manualStopLossPercent = sl, manualTakeProfitPercent = tp, riskReferenceMode = referenceMode)
        } else {
            TradingConfig(totalCapitalIdr = totalCapital, mode = mode, decisionMode = DecisionMode.SUGGESTION, riskReferenceMode = referenceMode)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_START = "com.mirei.app.action.START"
        const val ACTION_HOLD = "com.mirei.app.action.HOLD"
        const val ACTION_STOP = "com.mirei.app.action.STOP"
        const val ACTION_CLOSE_ALL = "com.mirei.app.action.CLOSE_ALL"
        const val ACTION_TOP_UP = "com.mirei.app.action.TOP_UP"
        const val ACTION_REFRESH = "com.mirei.app.action.REFRESH"
        const val ACTION_APPLY_RISK = "com.mirei.app.action.APPLY_RISK"
        const val ACTION_DELETE_HISTORY = "com.mirei.app.action.DELETE_HISTORY"
        const val ACTION_HUMAN_VERIFY = "com.mirei.app.action.HUMAN_VERIFY"
        const val ACTION_RESET_SESSION = "com.mirei.app.action.RESET_SESSION"
        const val ACTION_RESET_CLOCK = "com.mirei.app.action.RESET_CLOCK"
        const val ACTION_STATUS = "com.mirei.app.action.STATUS"
        const val EXTRA_STATE = "state"
        const val EXTRA_SYMBOL = "symbol"
        const val EXTRA_EXCHANGE = "exchange"
        const val EXTRA_INITIAL_ALLOCATIONS = "initial_allocations"
        const val EXTRA_HUMAN_SYMBOL = "human_symbol"
        const val EXTRA_HUMAN_AGENTS = "human_agents"
        const val EXTRA_TOP_UP_AMOUNT = "top_up_amount"
        const val EXTRA_TOTAL_CAPITAL = "total_capital"
        const val EXTRA_PRICE = "price"
        const val EXTRA_BID = "bid"
        const val EXTRA_ASK = "ask"
        const val EXTRA_HIGH_24H = "high24h"
        const val EXTRA_LOW_24H = "low24h"
        const val EXTRA_VOLUME_24H = "volume24h"
        const val EXTRA_EQUITY = "equity"
        const val EXTRA_BALANCE = "balance"
        const val EXTRA_PNL = "pnl"
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
        const val EXTRA_FLOW = "flow"
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
        const val EXTRA_BUY_COUNT = "buy_count"
        const val EXTRA_HOLD_COUNT = "hold_count"
        const val EXTRA_SELL_COUNT = "sell_count"
        const val EXTRA_HUMAN_REQUIRED = "human_required"
        const val EXTRA_HUMAN_ALLOWED = "human_allowed"
        const val EXTRA_HUMAN_BLOCKED = "human_blocked"
        const val EXTRA_SESSION_CREATED = "session_created"
        const val EXTRA_RUN_STARTED = "run_started"
        const val EXTRA_RUN_STOPPED = "run_stopped"
        const val EXTRA_CLOCK_RESET = "clock_reset"
        const val EXTRA_RISK_BASIS = "risk_basis"
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
        private const val KEY_RISK_BASIS = "risk_basis"
        private const val KEY_TOTAL_CAPITAL = "total_capital"
    }
}
