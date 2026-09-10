package com.mirei.app

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var status: TextView
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID"))
    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != MireiForegroundService.ACTION_STATUS) return
            renderStatus(intent)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        numberFormat.maximumFractionDigits = 2

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 40, 32, 32)
        }
        content.addView(TextView(this).apply {
            text = "Mirei ミレイ"
            textSize = 30f
        }, LinearLayout.LayoutParams(MATCH_PARENT, -2))
        content.addView(TextView(this).apply {
            text = "Android-first trading runtime"
            textSize = 16f
        }, LinearLayout.LayoutParams(MATCH_PARENT, -2))
        status = TextView(this).apply {
            text = "\nState: STOP\nMode: Suggestion\nExecution: PAPER ONLY\n\nSYSTEM HEALTH\nMarket data: OFFLINE\nInternet: UNKNOWN\nExchange: UNKNOWN"
            textSize = 17f
            setLineSpacing(0f, 1.05f)
        }
        content.addView(status, LinearLayout.LayoutParams(MATCH_PARENT, -2).apply {
            topMargin = 24
            bottomMargin = 16
        })
        content.addView(actionButton("START") { sendAction(MireiForegroundService.ACTION_START, "RUNNING") })
        content.addView(actionButton("HOLD") { sendAction(MireiForegroundService.ACTION_HOLD, "HOLD") })
        content.addView(actionButton("STOP") { sendAction(MireiForegroundService.ACTION_STOP, "STOP") })
        content.addView(actionButton("CLOSE ALL") { sendAction(MireiForegroundService.ACTION_CLOSE_ALL, "CLOSE_ALL") })

        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            addView(content, ScrollView.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        }
        setContentView(scrollView)
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(MireiForegroundService.ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(statusReceiver, filter, RECEIVER_NOT_EXPORTED) else registerReceiver(statusReceiver, filter)
    }

    override fun onStop() {
        runCatching { unregisterReceiver(statusReceiver) }
        super.onStop()
    }

    private fun actionButton(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        setOnClickListener { action() }
    }

    private fun sendAction(command: String, nextState: String) {
        try {
            val intent = Intent(this, MireiForegroundService::class.java).setAction(command)
            if (command == MireiForegroundService.ACTION_START && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
            status.text = """
                State: $nextState
                Mode: Suggestion
                Execution: PAPER ONLY

                SYSTEM HEALTH
                Waiting for runtime telemetry...

                MARKET
                Waiting for live market data...

                DECISION
                Waiting for agent evaluation...
            """.trimIndent()
        } catch (error: Exception) {
            status.text = """
                State: ERROR
                Mode: Suggestion
                Execution: PAPER ONLY

                SERVICE ERROR
                ${error.javaClass.simpleName}
            """.trimIndent()
        }
    }

    private fun renderStatus(intent: Intent) {
        val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "UNKNOWN"
        val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0)
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val balance = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0)
        val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        val confidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0)
        val rationale = intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE) ?: "no_decision"
        val agentSummary = intent.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty()
        val entryReasons = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty()
        val momentum = intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0)
        val sentiment = intent.getDoubleExtra(MireiForegroundService.EXTRA_SENTIMENT, 0.0)
        val forecast = intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0)
        val marketFresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        val internet = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
        val exchange = intent.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)
        val error = intent.getStringExtra(MireiForegroundService.EXTRA_ERROR)
        val health = if (marketFresh && internet && exchange && error.isNullOrBlank()) "HEALTHY" else "DEGRADED / SAFE HOLD"
        status.text = """
            STATE
            State: $state
            Mode: Suggestion
            Execution: PAPER ONLY

            SYSTEM HEALTH: $health
            Market data: ${if (marketFresh) "LIVE / FRESH" else "STALE / UNAVAILABLE"}
            Internet: ${if (internet) "ONLINE" else "OFFLINE"}
            Exchange: ${if (exchange) "REACHABLE" else "UNHEALTHY"}

            MARKET
            BTC/IDR: ${numberFormat.format(price)}
            Momentum: ${"%.4f".format(Locale.US, momentum)}%
            Sentiment: ${"%.1f".format(Locale.US, sentiment)}
            Forecast confidence: ${"%.2f".format(Locale.US, forecast)}

            ACCOUNT
            Equity: Rp ${numberFormat.format(equity)}
            Available: Rp ${numberFormat.format(balance)}
            Daily PnL: Rp ${numberFormat.format(pnl)}
            Positions: $positions

            DECISION
            Last action: $action (${(confidence * 100).toInt()}%)
            Reason: $rationale
            Entry gates: ${entryReasons.ifBlank { "none" }}

            AGENTS
            ${agentSummary.ifBlank { "not evaluated" }}
            ${if (error.isNullOrBlank()) "" else "\nERROR\n$error"}
        """.trimIndent()
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
    }

    companion object { private const val REQUEST_NOTIFICATIONS = 2001 }
}
