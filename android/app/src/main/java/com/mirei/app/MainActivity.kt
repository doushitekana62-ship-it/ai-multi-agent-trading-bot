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
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var marketSelector: Spinner
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID"))
    private val percentFormat = "%.4f"
    private val prefs by lazy { getSharedPreferences("mirei_settings", MODE_PRIVATE) }
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
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, -2))
        content.addView(TextView(this).apply {
            text = "Android-first trading runtime · live market telemetry"
            textSize = 16f
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, -2))

        content.addView(TextView(this).apply {
            text = "MARKET SELECTION"
            textSize = 17f
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, -2).apply {
            topMargin = 24
        })
        marketSelector = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity,
                android.R.layout.simple_spinner_dropdown_item,
                MireiForegroundService.SUPPORTED_MARKETS,
            )
            val saved = prefs.getString("market_symbol", MireiForegroundService.DEFAULT_SYMBOL)
            val index = MireiForegroundService.SUPPORTED_MARKETS.indexOf(saved)
            setSelection(index.coerceAtLeast(0))
            setOnItemSelectedListener(object : android.widget.AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                    prefs.edit().putString("market_symbol", MireiForegroundService.SUPPORTED_MARKETS[position]).apply()
                }
                override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            })
        }
        content.addView(marketSelector, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, -2))

        status = TextView(this).apply {
            text = "\nSTATE\nState: STOP\nMode: Suggestion\nExecution: PAPER ONLY\n\nSYSTEM HEALTH\nMarket data: OFFLINE\nInternet: UNKNOWN\nExchange: UNKNOWN"
            textSize = 17f
            setLineSpacing(0f, 1.05f)
        }
        content.addView(status, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, -2).apply {
            topMargin = 24
            bottomMargin = 16
        })
        content.addView(actionButton("START") { sendAction(MireiForegroundService.ACTION_START, "RUNNING") })
        content.addView(actionButton("HOLD") { sendAction(MireiForegroundService.ACTION_HOLD, "HOLD") })
        content.addView(actionButton("STOP") { sendAction(MireiForegroundService.ACTION_STOP, "STOP") })
        content.addView(actionButton("CLOSE ALL") { sendAction(MireiForegroundService.ACTION_CLOSE_ALL, "CLOSE_ALL") })

        val scrollView = ScrollView(this).apply {
            isFillViewport = true
            addView(content, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
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
            val selected = MireiForegroundService.SUPPORTED_MARKETS.getOrNull(marketSelector.selectedItemPosition)
                ?: MireiForegroundService.DEFAULT_SYMBOL
            val intent = Intent(this, MireiForegroundService::class.java).setAction(command).apply {
                putExtra(MireiForegroundService.EXTRA_SYMBOL, selected)
            }
            if (command == MireiForegroundService.ACTION_START && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
            status.text = """
                STATE
                State: $nextState
                Mode: Suggestion
                Execution: PAPER ONLY
                Market: $selected

                SYSTEM HEALTH
                Waiting for runtime telemetry...

                MARKET
                Waiting for live market data...
            """.trimIndent()
        } catch (error: Exception) {
            status.text = """
                STATE
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
        val symbol = intent.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: MireiForegroundService.DEFAULT_SYMBOL
        val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0)
        val bid = intent.getDoubleExtra(MireiForegroundService.EXTRA_BID, 0.0)
        val ask = intent.getDoubleExtra(MireiForegroundService.EXTRA_ASK, 0.0)
        val high24h = intent.getDoubleExtra(MireiForegroundService.EXTRA_HIGH_24H, 0.0)
        val low24h = intent.getDoubleExtra(MireiForegroundService.EXTRA_LOW_24H, 0.0)
        val volume24h = intent.getDoubleExtra(MireiForegroundService.EXTRA_VOLUME_24H, 0.0)
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val balance = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0)
        val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        val confidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0)
        val rationale = intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE) ?: "no_decision"
        val agentSummary = intent.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty()
        val entryReasons = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty()
        val momentum = intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0)
        val volatility = intent.getDoubleExtra(MireiForegroundService.EXTRA_VOLATILITY, 0.0)
        val sentiment = intent.getDoubleExtra(MireiForegroundService.EXTRA_SENTIMENT, 0.0)
        val forecast = intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0)
        val spread = intent.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0)
        val changeTick = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_TICK, 0.0)
        val change1m = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0)
        val change5m = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0)
        val change15m = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0)
        val flow = intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0)
        val trend = intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0)
        val tradeCount = intent.getIntExtra(MireiForegroundService.EXTRA_TRADE_COUNT, 0)
        val buyVolume = intent.getDoubleExtra(MireiForegroundService.EXTRA_BUY_VOLUME, 0.0)
        val sellVolume = intent.getDoubleExtra(MireiForegroundService.EXTRA_SELL_VOLUME, 0.0)
        val lastTrade = intent.getLongExtra(MireiForegroundService.EXTRA_LAST_TRADE, 0L)
        val snapshotTime = intent.getLongExtra(MireiForegroundService.EXTRA_SNAPSHOT_TIME, 0L)
        val sourceAge = intent.getLongExtra(MireiForegroundService.EXTRA_SOURCE_AGE, 0L)
        val marketFresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        val internet = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
        val exchange = intent.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)
        val error = intent.getStringExtra(MireiForegroundService.EXTRA_ERROR)
        val health = if (marketFresh && internet && exchange && error.isNullOrBlank()) "HEALTHY" else "DEGRADED / SAFE HOLD"

        if (::marketSelector.isInitialized) {
            marketSelector.isEnabled = state != "RUNNING"
            val index = MireiForegroundService.SUPPORTED_MARKETS.indexOf(symbol)
            if (index >= 0 && marketSelector.selectedItemPosition != index) marketSelector.setSelection(index)
        }

        status.text = """
            STATE
            State: $state
            Mode: Suggestion
            Execution: PAPER ONLY
            Market: $symbol

            SYSTEM HEALTH: $health
            Market data: ${if (marketFresh) "LIVE / FRESH" else "STALE / UNAVAILABLE"}
            Source age: ${sourceAge}ms
            Internet: ${if (internet) "ONLINE" else "OFFLINE"}
            Exchange: ${if (exchange) "REACHABLE" else "UNHEALTHY"}

            MARKET
            Last price: ${numberFormat.format(price)}
            Bid / Ask: ${numberFormat.format(bid)} / ${numberFormat.format(ask)}
            Spread: ${percentFormat.format(Locale.US, spread)}%
            24H high / low: ${numberFormat.format(high24h)} / ${numberFormat.format(low24h)}
            24H volume: ${numberFormat.format(volume24h)}

            PRICE CHANGE
            Since last tick: ${percentFormat.format(Locale.US, changeTick)}%
            1m: ${percentFormat.format(Locale.US, change1m)}%
            5m: ${percentFormat.format(Locale.US, change5m)}%
            15m: ${percentFormat.format(Locale.US, change15m)}%
            Momentum: ${percentFormat.format(Locale.US, momentum)}%
            Volatility: ${percentFormat.format(Locale.US, volatility)}%
            Trend score: ${percentFormat.format(Locale.US, trend)}%

            FLOW / SENTIMENT
            Trade count: $tradeCount
            Buy volume: ${numberFormat.format(buyVolume)}
            Sell volume: ${numberFormat.format(sellVolume)}
            Trade flow: ${percentFormat.format(Locale.US, flow)}%
            Sentiment: ${percentFormat.format(Locale.US, sentiment)}
            Forecast confidence: ${percentFormat.format(Locale.US, forecast)}

            DATA TIME
            Last trade: ${formatEpoch(lastTrade)}
            Snapshot: ${formatEpoch(snapshotTime)}

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

    private fun formatEpoch(epochMs: Long): String {
        if (epochMs <= 0L) return "n/a"
        return SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(Date(epochMs))
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
    }

    companion object { private const val REQUEST_NOTIFICATIONS = 2001 }
}
