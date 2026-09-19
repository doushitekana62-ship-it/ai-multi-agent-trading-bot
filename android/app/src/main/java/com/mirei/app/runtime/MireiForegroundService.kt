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
import com.mirei.app.core.Exchange
import com.mirei.app.core.MireiState
import com.mirei.app.core.PositionTradeConfigStore
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.TradingConfig
import com.mirei.app.core.TradingUniverse
import com.mirei.app.execution.PaperEngineState
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.PaperSessionSnapshot
import com.mirei.app.storage.PaperSessionStore
import com.mirei.app.storage.TradeLedgerFactory

class MireiForegroundService : Service() {
    private var state = MireiState.STOP
    private var config = TradingConfig()
    private var symbol = DEFAULT_SYMBOL
    private var exchangeId = DEFAULT_EXCHANGE
    private var managedSymbols = listOf(DEFAULT_SYMBOL)
    private var sessionStarted = false
    private var sessionCreatedAtEpochMs = 0L
    private var runStartedAtEpochMs = 0L
    private var runStoppedAtEpochMs = 0L
    private var sessionOpeningCapitalIdr = 0.0
    private lateinit var workerThread: HandlerThread
    private lateinit var worker: Handler
    private lateinit var runtime: MireiPaperTradingRuntime
    private lateinit var marketData: PaperMarketDataSource
    private lateinit var prefs: SharedPreferences
    private lateinit var sessionStore: PaperSessionStore
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var internetAvailable = false
    private var lastNotificationKey = ""
    private var pausedSymbols: Set<String> = emptySet()

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        sessionStore = PaperSessionStore(this)
        PositionTradeConfigStore.reload(this)
        config = loadConfig()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Mirei Runtime", NotificationManager.IMPORTANCE_LOW)
        )
        workerThread = HandlerThread("mirei-runtime-worker").also { it.start() }
        worker = Handler(workerThread.looper)
        marketData = MultiMarketDataSource()

        val saved = sessionStore.load()
        if (saved?.active == true) restoreSessionMetadata(saved)
        createRuntime()
        if (saved?.active == true) restoreRuntimeState(saved)

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
                if (state == MireiState.RUNNING) state = MireiState.HOLD
                publishHealth()
            }
        }
        networkCallback = callback
        connectivity.registerDefaultNetworkCallback(callback)
        publishHealth()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, notification(stateLabel()))
        when (intent?.action) {
            ACTION_STATUS -> publishHealth()
            ACTION_START -> startRuntime(intent)
            ACTION_RESUME -> resumeRuntime()
            ACTION_HOLD -> holdRuntime()
            ACTION_STOP -> stopRuntime()
            ACTION_CLOSE_ALL -> closeAll()
            ACTION_STOP_SELECTED -> stopSelected(intent)
            ACTION_APPLY_RISK -> applyRisk()
            ACTION_RESET_SESSION -> resetSession()
        }
        return START_NOT_STICKY
    }

    private fun startRuntime(intent: Intent) {
        if (!isRiskConfigured()) {
            audit("START_REJECTED", "sl_tp_setup_required")
            state = MireiState.STOP
            publishHealth()
            return
        }
        val allocationsRaw = intent.getStringExtra(EXTRA_INITIAL_ALLOCATIONS).orEmpty()
        val hasAllocations = allocationsRaw.isNotBlank()

        if (sessionStarted && hasAllocations) {
            if (state != MireiState.STOP) {
                audit("START_REJECTED", "stop_before_new_session")
                return
            }
            sessionStore.clearSession()
            sessionStarted = false
            config = loadConfig()
            createRuntime()
        }

        if (sessionStarted) {
            val resumeStatus = runtime.status(RuntimeEnvironment(internetAvailable, exchangeId in SUPPORTED_EXCHANGES))
            val hasRecoveryCycle = resumeStatus.mireiCycles.values.any { it.state == com.mirei.app.core.MireiCycleState.REENTRY_WAIT }
            if (runtime.paperEngine().positionCount() <= 0 && !hasRecoveryCycle) {
                audit("START_REJECTED", "no_active_positions")
                state = MireiState.STOP
                publishHealth()
                return
            }
            if (!internetAvailable) {
                state = MireiState.HOLD
                publishHealth()
                return
            }
            worker.removeCallbacksAndMessages(null)
            worker.post {
                state = MireiState.RUNNING
                runStartedAtEpochMs = System.currentTimeMillis()
                runStoppedAtEpochMs = 0L
                persistSession()
                publishHealth()
                worker.post(runtimeLoop)
            }
            return
        }

        val allocations = parseAllocations(allocationsRaw)
        if (allocations.isEmpty()) {
            audit("START_FAILED", "initial_holdings_required")
            state = MireiState.STOP
            publishHealth()
            return
        }
        if (allocations.size > config.maxOpenPositions) {
            audit("START_FAILED", "too_many_positions")
            state = MireiState.STOP
            publishHealth()
            return
        }
        if (allocations.values.sum() > config.totalCapitalIdr + 1e-6) {
            audit("START_FAILED", "allocation_exceeds_session_capital")
            state = MireiState.STOP
            publishHealth()
            return
        }

        symbol = intent.getStringExtra(EXTRA_SYMBOL)?.takeIf { it in SUPPORTED_MARKETS } ?: allocations.keys.first()
        managedSymbols = allocations.keys.take(config.maxOpenPositions)
        exchangeId = TradingUniverse.bySymbol(symbol)?.providerId ?: DEFAULT_EXCHANGE
        if (exchangeId !in SUPPORTED_EXCHANGES) {
            audit("START_FAILED", "exchange_not_supported")
            state = MireiState.STOP
            publishHealth()
            return
        }

        config = loadConfig()
        createRuntime()
        worker.removeCallbacksAndMessages(null)
        worker.post {
            runCatching {
                val seeded = runtime.seedInitialHoldings(allocations, System.currentTimeMillis())
                require(seeded.size == allocations.size && seeded.all { it.success }) { "initial_position_not_created" }
                require(runtime.paperEngine().positionCount() > 0) { "initial_position_not_created" }
                val now = System.currentTimeMillis()
                sessionStarted = true
                sessionCreatedAtEpochMs = now
                sessionOpeningCapitalIdr = config.totalCapitalIdr
                runStartedAtEpochMs = now
                runStoppedAtEpochMs = 0L
                state = MireiState.RUNNING
                persistSession()
                publishHealth()
                worker.post(runtimeLoop)
            }.onFailure {
                state = MireiState.STOP
                audit("START_FAILED", it.message ?: "unknown_error")
                publishHealth()
            }
        }
    }

    private fun holdRuntime() {
        if (!sessionStarted) return
        state = MireiState.HOLD
        worker.removeCallbacksAndMessages(null)
        runStoppedAtEpochMs = System.currentTimeMillis()
        persistSession()
        audit("SESSION_HOLD", "hold")
        publishHealth()
    }

    private fun stopRuntime() {
        state = MireiState.STOP
        worker.removeCallbacksAndMessages(null)
        runStoppedAtEpochMs = System.currentTimeMillis()
        persistSession()
        audit("SESSION_STOPPED", "stop")
        publishHealth()
    }

    private fun resetSession() {
        state = MireiState.STOP
        worker.removeCallbacksAndMessages(null)
        sessionStarted = false
        sessionCreatedAtEpochMs = 0L
        runStartedAtEpochMs = 0L
        runStoppedAtEpochMs = System.currentTimeMillis()
        sessionStore.clearSession()
        config = loadConfig()
        createRuntime()
        audit("SESSION_RESET", "portfolio_reset")
        publishHealth()
    }

    private fun isRiskConfigured(): Boolean =
        prefs.getBoolean("sl_tp_configured", false) && PositionTradeConfigStore.snapshot()["*"] != null

    private fun applyRisk() {
        PositionTradeConfigStore.reload(this)
        config = loadConfig()
        if (sessionStarted) runtime.applyRiskConfig(config)
        audit("SL_TP_APPLIED", "profiles=${config.positionProfiles.keys.joinToString(",")}")
        publishHealth()
    }

    private val runtimeLoop = object : Runnable {
        override fun run() {
            if (state != MireiState.RUNNING || !sessionStarted) return
            val now = System.currentTimeMillis()
            val status = runtime.tick(now, RuntimeEnvironment(internetAvailable, exchangeId in SUPPORTED_EXCHANGES))
            persistExecutions(status)
            persistMireiDecisions(status)
            persistSession()
            publishStatus(status)
            if (state == MireiState.RUNNING && sessionStarted) worker.postDelayed(this, TICK_MS)
        }
    }

    private fun stopSelected(intent: Intent) {
        val symbols = intent.getStringArrayListExtra(EXTRA_SELECTED_SYMBOLS)?.toSet().orEmpty()
        if (symbols.isEmpty()) return
        worker.post {
            pausedSymbols = pausedSymbols + symbols
            runtime.pauseSymbols(symbols)
            state = MireiState.STOP
            runStoppedAtEpochMs = System.currentTimeMillis()
            persistSession()
            audit("POSITIONS_STOPPED", "symbols=${symbols.joinToString(",")}")
            publishHealth()
        }
    }
    private fun resumeRuntime() {
        if (!sessionStarted) {
            audit("RESUME_REJECTED", "no_session")
            publishHealth()
            return
        }
        worker.post {
            pausedSymbols = emptySet()
            runtime.resumeAll()
            if (!internetAvailable) {
                state = MireiState.HOLD
                publishHealth()
                return@post
            }
            state = MireiState.RUNNING
            runStartedAtEpochMs = System.currentTimeMillis()
            runStoppedAtEpochMs = 0L
            worker.removeCallbacksAndMessages(null)
            persistSession()
            audit("POSITIONS_RESUMED", "all")
            publishHealth()
            worker.post(runtimeLoop)
        }
    }

    private fun closeAll() {
        worker.post {
            val status = runtime.closeAll(System.currentTimeMillis(), RuntimeEnvironment(internetAvailable, exchangeId in SUPPORTED_EXCHANGES))
            persistExecutions(status)
            persistMireiDecisions(status)
            if (status.activePositions.isEmpty()) {
                state = MireiState.STOP
                runStoppedAtEpochMs = System.currentTimeMillis()
            }
            persistSession()
            publishStatus(status)
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

    private fun restoreSessionMetadata(saved: PaperSessionSnapshot) {
        sessionStarted = true
        sessionCreatedAtEpochMs = saved.sessionCreatedAtEpochMs
        runStartedAtEpochMs = saved.runStartedAtEpochMs
        runStoppedAtEpochMs = saved.runStoppedAtEpochMs
        sessionOpeningCapitalIdr = saved.sessionOpeningCapitalIdr
        symbol = saved.symbol.ifBlank { DEFAULT_SYMBOL }
        exchangeId = saved.exchangeId.ifBlank { TradingUniverse.bySymbol(symbol)?.providerId ?: DEFAULT_EXCHANGE }
        managedSymbols = saved.managedSymbols.ifEmpty { listOf(symbol) }.take(config.maxOpenPositions)
    }

    private fun restoreRuntimeState(saved: PaperSessionSnapshot) {
        runtime.restoreState(
            PaperRuntimePersistence(
                engineState = PaperEngineState(saved.availableBalanceIdr, saved.positions),
                dailyPnlIdr = saved.dailyPnlIdr,
                consecutiveLosses = saved.consecutiveLosses,
                holdingsSeeded = saved.holdingsSeeded,
                initialCapitalBySymbol = saved.initialCapitalBySymbol,
                mireiCycles = saved.mireiCycles,
                pausedSymbols = saved.pausedSymbols,
                sessionOpeningCapitalIdr = saved.sessionOpeningCapitalIdr,
                lastMarkPriceBySymbol = saved.lastMarkPriceBySymbol,
            )
        )
    }

    private fun persistSession() {
        if (!sessionStarted) return
        val stateSnapshot = runtime.persistenceState()
        sessionStore.save(
            PaperSessionSnapshot(
                active = true,
                sessionCreatedAtEpochMs = sessionCreatedAtEpochMs,
                runStartedAtEpochMs = runStartedAtEpochMs,
                runStoppedAtEpochMs = runStoppedAtEpochMs,
                timestampResetAtEpochMs = 0L,
                symbol = symbol,
                exchangeId = exchangeId,
                managedSymbols = managedSymbols,
                availableBalanceIdr = stateSnapshot.engineState.availableBalanceIdr,
                dailyPnlIdr = stateSnapshot.dailyPnlIdr,
                consecutiveLosses = stateSnapshot.consecutiveLosses,
                holdingsSeeded = stateSnapshot.holdingsSeeded,
                positions = stateSnapshot.engineState.positions,
                buyDecisionCount = 0,
                holdDecisionCount = 0,
                sellDecisionCount = 0,
                initialCapitalBySymbol = stateSnapshot.initialCapitalBySymbol,
                positionProfiles = PositionTradeConfigStore.snapshot(),
                mireiCycles = stateSnapshot.mireiCycles,
                pausedSymbols = stateSnapshot.pausedSymbols,
                sessionOpeningCapitalIdr = stateSnapshot.sessionOpeningCapitalIdr,
                lastMarkPriceBySymbol = stateSnapshot.lastMarkPriceBySymbol,
            )
        )
        val continuityDelta = runtime.capitalContinuityDeltaIdr()
        if (kotlin.math.abs(continuityDelta) > 0.5) {
            audit("CAPITAL_CONTINUITY_MISMATCH", "delta=$continuityDelta|opening=$sessionOpeningCapitalIdr")
        }
    }

    private fun persistMireiDecisions(status: PaperRuntimeStatus) {
        status.mireiDecisions.forEach { decision ->
            audit(
                "MIREI_" + decision.action.name,
                "symbol=" + decision.symbol +
                    "|cycle=" + decision.cycleId +
                    "|seq=" + decision.sequence +
                    "|reason=" + decision.reason +
                    "|reference=" + decision.referenceCapitalIdr,
                status.lastTickEpochMs
            )
        }
    }

    private fun persistExecutions(status: PaperRuntimeStatus) {
        status.recentExecutions.forEach { execution ->
            val event = when (execution.reason) {
                "stop_loss" -> "SL_SELL"
                "take_profit" -> "TP_SELL"
                "re_entry" -> "RE_ENTRY_BUY"
                "manual_close_all" -> "MANUAL_SELL"
                "initial_holding_seeded" -> "INITIAL_BUY"
                else -> "EXECUTION"
            }
            audit(event, "symbol=${status.marketSymbol}|reason=${execution.reason}|price=${execution.averagePrice}|pnl=${execution.pnlIdr}", status.lastTickEpochMs)
        }
    }

    private fun publishHealth() = publishStatus(runtime.status(RuntimeEnvironment(internetAvailable, exchangeId in SUPPORTED_EXCHANGES)))

    private fun publishStatus(status: PaperRuntimeStatus) {
        val intent = Intent(ACTION_STATUS).apply {
            setPackage(packageName)
            putExtra(EXTRA_STATE, state.name)
            putExtra(EXTRA_SYMBOL, status.marketSymbol)
            putExtra(EXTRA_EXCHANGE, exchangeId)
            putExtra(EXTRA_PRICE, status.marketPrice)
            putExtra(EXTRA_EQUITY, status.equityIdr)
            putExtra(EXTRA_BALANCE, status.availableBalanceIdr)
            putExtra(EXTRA_PNL, status.dailyPnlIdr)
            putExtra(EXTRA_POSITIONS, status.activePositions.size)
            putExtra(EXTRA_MARKET_FRESH, status.marketDataFresh)
            putExtra(EXTRA_INTERNET, status.internetAvailable)
            putExtra(EXTRA_ERROR, status.lastError ?: "")
            putExtra(EXTRA_SESSION_CREATED, sessionCreatedAtEpochMs)
            putExtra(EXTRA_LAST_TICK, status.lastTickEpochMs)
            putExtra(EXTRA_POSITIONS_DETAIL, status.activePositions.joinToString("\n") { position ->
                val pnl = status.activePositionPnlIdr[position.symbol] ?: 0.0
                val gross = status.activePositionGrossPnlIdr[position.symbol] ?: pnl
                val fee = status.activePositionFeeIdr[position.symbol] ?: 0.0
                val mark = status.activePositionMarkPrice[position.symbol] ?: position.entryPrice
                val trend = status.activePositionTrend[position.symbol] ?: "FLAT"
                val reentry = status.activePositionReentryCount[position.symbol] ?: 0
                val cycle = status.mireiCycles[position.symbol]
                "${position.symbol}|${position.stakeIdr}|${position.entryPrice}|${position.stopLossPrice}|${position.takeProfitPrice}|${pnl}|${gross}|${fee}|${mark}|${trend}|${reentry}|${cycle?.state?.name ?: "HOLDING"}|${cycle?.lastDecision?.name ?: "HOLD"}"
            })
        }
        sendBroadcast(intent)

        val execution = status.recentExecutions.lastOrNull()
        val message = when {
            execution?.reason == "stop_loss" -> "SELL ${status.marketSymbol} · SL"
            execution?.reason == "take_profit" -> "SELL ${status.marketSymbol} · TP"
            execution?.reason == "re_entry" -> "BUY ${status.marketSymbol} · RE-ENTRY"
            !status.lastError.isNullOrBlank() -> "HOLD · ${status.lastError}"
            state == MireiState.RUNNING -> "RUNNING · HOLD sampai SL/TP"
            state == MireiState.HOLD -> "HOLD"
            else -> "STOP"
        }
        publish(message)
    }

    private fun audit(type: String, details: String, nowMs: Long = System.currentTimeMillis()) {
        runCatching { MireiDatabase(this).recordAudit(type, details, nowMs) }
    }

    private fun publish(text: String) {
        if (text == lastNotificationKey) return
        lastNotificationKey = text
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification =
        Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Mirei · Paper")
            .setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text))
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()

    private fun stateLabel(): String = when (state) {
        MireiState.RUNNING -> "BERJALAN"
        MireiState.HOLD -> "HOLD"
        MireiState.STOP -> "BERHENTI"
        else -> state.name
    }

    private fun loadConfig(): TradingConfig {
        val totalCapital = prefs.getString(KEY_TOTAL_CAPITAL, null)?.toDoubleOrNull()?.takeIf { it > 0.0 } ?: 150_000.0
        val firstProfile = PositionTradeConfigStore.snapshot().values.firstOrNull()
        return TradingConfig(
            totalCapitalIdr = totalCapital,
            positionSizeIdr = 50_000.0,
            maxOpenPositions = 10,
            manualStopLossPercent = firstProfile?.stopLossPercent ?: 0.50,
            manualNetProfitTargetIdr = firstProfile?.manualNetProfitTargetIdr ?: 30.0,
            riskReferenceMode = firstProfile?.riskReferenceMode ?: RiskReferenceMode.ENTRY_PRICE,
            positionProfiles = PositionTradeConfigStore.snapshot(),
        )
    }

    override fun onDestroy() {
        runCatching { persistSession() }
        runCatching { networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) } }
        runCatching { workerThread.quitSafely() }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_START = "com.mirei.app.action.START"
        const val ACTION_RESUME = "com.mirei.app.action.RESUME"
        const val ACTION_HOLD = "com.mirei.app.action.HOLD"
        const val ACTION_STOP = "com.mirei.app.action.STOP"
        const val ACTION_CLOSE_ALL = "com.mirei.app.action.CLOSE_ALL"
        const val ACTION_STOP_SELECTED = "com.mirei.app.action.STOP_SELECTED"
        const val ACTION_APPLY_RISK = "com.mirei.app.action.APPLY_RISK"
        const val ACTION_RESET_SESSION = "com.mirei.app.action.RESET_SESSION"
        const val ACTION_STATUS = "com.mirei.app.action.STATUS"

        const val EXTRA_STATE = "state"
        const val EXTRA_SYMBOL = "symbol"
        const val EXTRA_EXCHANGE = "exchange"
        const val EXTRA_INITIAL_ALLOCATIONS = "initial_allocations"
        const val EXTRA_PRICE = "price"
        const val EXTRA_EQUITY = "equity"
        const val EXTRA_BALANCE = "balance"
        const val EXTRA_PNL = "pnl"
        const val EXTRA_POSITIONS = "positions"
        const val EXTRA_MARKET_FRESH = "market_fresh"
        const val EXTRA_INTERNET = "internet"
        const val EXTRA_ERROR = "error"
        const val EXTRA_POSITIONS_DETAIL = "positions_detail"
        const val EXTRA_SESSION_CREATED = "session_created"
        const val EXTRA_LAST_TICK = "last_tick"
        const val EXTRA_SELECTED_SYMBOLS = "selected_symbols"

        const val DEFAULT_SYMBOL = "BTC/IDR"
        const val DEFAULT_EXCHANGE = "indodax"
        val SUPPORTED_MARKETS: List<String> get() = TradingUniverse.paperReady().map { it.symbol }
        val SUPPORTED_EXCHANGES: List<String> get() = Exchange.values().map { it.id }

        private const val CHANNEL_ID = "mirei_runtime"
        private const val NOTIFICATION_ID = 1001
        private const val TICK_MS = 5_000L
        private const val PREFS_NAME = "mirei_settings"
        private const val KEY_TOTAL_CAPITAL = "total_capital"
    }
}
