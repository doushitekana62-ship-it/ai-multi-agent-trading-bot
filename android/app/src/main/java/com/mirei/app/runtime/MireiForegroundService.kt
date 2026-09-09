package com.mirei.app.runtime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import com.mirei.app.core.MireiState
import com.mirei.app.storage.TradeLedgerFactory

class MireiForegroundService : Service() {
    private val controller = MireiRuntimeController()
    private val config = com.mirei.app.core.TradingConfig()
    private val symbol = "BTC/IDR"
    private lateinit var workerThread: HandlerThread
    private lateinit var worker: Handler
    private lateinit var runtime: MireiPaperTradingRuntime
    private lateinit var marketData: IndodaxMarketDataSource
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var internetAvailable = false

    override fun onCreate() {
        super.onCreate()
        try {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Mirei Runtime", NotificationManager.IMPORTANCE_LOW))

            workerThread = HandlerThread("mirei-runtime-worker").also { it.start() }
            worker = Handler(workerThread.looper)
            marketData = IndodaxMarketDataSource()
            runtime = MireiPaperTradingRuntime(
                config = config,
                marketData = marketData,
                tradeLedger = TradeLedgerFactory.create(this),
                symbol = symbol,
            )

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
            startForeground(NOTIFICATION_ID, notification("Mirei ${controller.state.name}"))
            when (intent?.action) {
                ACTION_START -> {
                    controller.start()
                    worker.removeCallbacksAndMessages(null)
                    worker.post(runtimeLoop)
                }
                ACTION_HOLD -> {
                    controller.hold()
                    worker.removeCallbacksAndMessages(null)
                    publishHealth()
                }
                ACTION_STOP -> {
                    controller.stop()
                    worker.removeCallbacksAndMessages(null)
                    publishHealth()
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
                ACTION_CLOSE_ALL -> {
                    controller.closeAll()
                    worker.post {
                        val status = runtime.closeAll(
                            nowMs = System.currentTimeMillis(),
                            environment = RuntimeEnvironment(internetAvailable = internetAvailable, exchangeHealthy = true),
                        )
                        if (status.activePositions.isEmpty()) {
                            controller.hold()
                        }
                        publishStatus(status)
                    }
                }
            }
        } catch (error: Exception) {
            handleRuntimeFailure("Mirei action failed", error)
        }
        return START_NOT_STICKY
    }

    private val runtimeLoop = object : Runnable {
        override fun run() {
            if (controller.state != MireiState.RUNNING) return
            val status = runtime.tick(
                System.currentTimeMillis(),
                RuntimeEnvironment(internetAvailable = internetAvailable, exchangeHealthy = true),
            )
            publishStatus(status)
            if (controller.state == MireiState.RUNNING) worker.postDelayed(this, TICK_MS)
        }
    }

    override fun onDestroy() {
        try {
            networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) }
        } catch (_: Exception) {
        }
        workerThread.takeIf { ::workerThread.isInitialized }?.quitSafely()
        networkCallback = null
        connectivityManager = null
        super.onDestroy()
    }

    private fun handleRuntimeFailure(message: String, error: Throwable) {
        controller.onEngineError()
        runCatching { publish("$message — Mirei ERROR") }
        runCatching { publishHealth() }
        stopSelf()
    }

    private fun publishStatus(status: PaperRuntimeStatus) {
        val intent = Intent(ACTION_STATUS).setPackage(packageName).apply {
            putExtra(EXTRA_STATE, controller.state.name)
            putExtra(EXTRA_PRICE, status.marketPrice)
            putExtra(EXTRA_EQUITY, status.equityIdr)
            putExtra(EXTRA_BALANCE, status.availableBalanceIdr)
            putExtra(EXTRA_PNL, status.dailyPnlIdr)
            putExtra(EXTRA_POSITIONS, status.activePositions.size)
            putExtra(EXTRA_CONFIDENCE, status.lastDecision?.confidence ?: 0.0)
            putExtra(EXTRA_ACTION, status.lastDecision?.action?.name ?: "HOLD")
            putExtra(EXTRA_RATIONALE, status.lastDecision?.rationale ?: "no_decision")
            putExtra(EXTRA_AGENT_SUMMARY, status.lastDecision?.observations?.joinToString(" | ") {
                "${it.agent.name}:${it.action.name} ${(it.confidence * 100).toInt()}% ${it.rationale}"
            } ?: "")
            putExtra(EXTRA_ENTRY_REASONS, status.entryPlanReasons.joinToString(" | "))
            putExtra(EXTRA_MOMENTUM, status.marketMomentumPercent)
            putExtra(EXTRA_SENTIMENT, status.marketSentimentScore)
            putExtra(EXTRA_FORECAST_CONFIDENCE, status.forecastConfidence)
            putExtra(EXTRA_MARKET_FRESH, status.marketDataFresh)
            putExtra(EXTRA_INTERNET, status.internetAvailable)
            putExtra(EXTRA_EXCHANGE_HEALTHY, status.exchangeHealthy)
            putExtra(EXTRA_ERROR, status.lastError)
            putExtra(EXTRA_TICK, status.lastTickEpochMs)
        }
        sendBroadcast(intent)
        publish("Mirei ${controller.state.name} · ${status.activePositions.size} position(s)")
    }

    private fun publishHealth() {
        val status = runtime.status(RuntimeEnvironment(internetAvailable = internetAvailable, exchangeHealthy = true))
        publishStatus(status)
    }

    private fun publish(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification = Notification.Builder(this, CHANNEL_ID)
        .setContentTitle("Mirei ミレイ")
        .setContentText(text)
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setOngoing(controller.state != MireiState.STOP)
        .build()

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_START = "com.mirei.app.action.START"
        const val ACTION_HOLD = "com.mirei.app.action.HOLD"
        const val ACTION_STOP = "com.mirei.app.action.STOP"
        const val ACTION_CLOSE_ALL = "com.mirei.app.action.CLOSE_ALL"
        const val ACTION_STATUS = "com.mirei.app.action.STATUS"
        const val EXTRA_STATE = "state"
        const val EXTRA_PRICE = "price"
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
        const val EXTRA_SENTIMENT = "sentiment"
        const val EXTRA_FORECAST_CONFIDENCE = "forecast_confidence"
        const val EXTRA_MARKET_FRESH = "market_fresh"
        const val EXTRA_INTERNET = "internet"
        const val EXTRA_EXCHANGE_HEALTHY = "exchange_healthy"
        const val EXTRA_ERROR = "error"
        const val EXTRA_TICK = "tick"
        private const val CHANNEL_ID = "mirei_runtime"
        private const val NOTIFICATION_ID = 1001
        private const val TICK_MS = 5_000L
    }
}
