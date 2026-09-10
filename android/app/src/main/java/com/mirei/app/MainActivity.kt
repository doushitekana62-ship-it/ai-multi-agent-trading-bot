package com.mirei.app

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.DecisionRow
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.TradeRow
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var dashboard: LinearLayout
    private lateinit var historyContainer: LinearLayout
    private lateinit var marketChart: SparklineView
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID"))
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, MODE_PRIVATE) }
    private val priceSeries = mutableListOf<Double>()
    private var screenRunning = false

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == MireiForegroundService.ACTION_STATUS) renderStatus(intent)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        numberFormat.maximumFractionDigits = 2
        buildStopScreen()
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

    private fun buildStopScreen() {
        screenRunning = false
        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(28, 36, 28, 28) }
        content.addView(title("Mirei ミレイ", 30f))
        content.addView(title("Android-first paper trading runtime", 16f))
        content.addView(card("PAPER BOOTSTRAP\nStarting capital: Rp 150.000\nInitial coins are supplied by you after pressing START.\nMirei never creates a BUY just to consume the starting capital."), marginParams(0, 22, 0, 12))
        status = TextView(this).apply { textSize = 16f; text = "STATE\nState: STOP\nExecution: PAPER ONLY\nPress START to define the initial portfolio." }
        content.addView(status, marginParams(0, 8, 0, 12))
        content.addView(actionButton("START") { showStartDialog() })
        content.addView(actionButton("REFRESH") { sendSimpleAction(MireiForegroundService.ACTION_REFRESH) })
        content.addView(actionButton("DELETE HISTORY") { confirmDeleteHistory() })
        dashboard = content
        setContentView(scroll(content))
    }

    private fun buildRunningScreen() {
        screenRunning = true
        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 28, 20, 28) }
        content.addView(title("Mirei ミレイ", 28f))
        content.addView(title("Live paper telemetry · runtime cycle 5s", 14f))
        status = TextView(this).apply { textSize = 15f; setLineSpacing(0f, 1.04f) }
        content.addView(status, marginParams(0, 18, 0, 10))
        marketChart = SparklineView(this)
        content.addView(cardView("MARKET PULSE / PRICE GRAPH", marketChart, 220))
        content.addView(actionButton("RISK / EXIT SETTINGS") { showRiskDialog() })
        content.addView(actionButton("REFRESH DATA") { sendSimpleAction(MireiForegroundService.ACTION_REFRESH) })
        content.addView(actionButton("HOLD") { sendSimpleAction(MireiForegroundService.ACTION_HOLD) })
        content.addView(actionButton("CLOSE ALL") { sendSimpleAction(MireiForegroundService.ACTION_CLOSE_ALL) })
        content.addView(actionButton("STOP") { sendSimpleAction(MireiForegroundService.ACTION_STOP) })
        content.addView(actionButton("DELETE HISTORY") { confirmDeleteHistory() })
        historyContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        content.addView(historyContainer, marginParams(0, 18, 0, 0))
        dashboard = content
        setContentView(scroll(content))
    }

    private fun scroll(view: View): ScrollView = ScrollView(this).apply { isFillViewport = true; addView(view, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)) }
    private fun title(text: String, size: Float): TextView = TextView(this).apply { this.text = text; textSize = size }
    private fun card(text: String): TextView = TextView(this).apply { this.text = text; textSize = 15f; setPadding(18, 18, 18, 18) }
    private fun cardView(label: String, view: View, height: Int): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; addView(title(label, 16f), marginParams(0, 8, 0, 4)); addView(view, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, height)) }
    private fun marginParams(l: Int, t: Int, r: Int, b: Int) = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }
    private fun actionButton(label: String, action: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { action() } }

    private fun showStartDialog() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 6, 20, 4) }
        root.addView(title("EXCHANGE", 14f)); val exchangeSpinner = spinner(MireiForegroundService.SUPPORTED_EXCHANGES.map(::exchangeLabel)); root.addView(exchangeSpinner)
        root.addView(title("INITIAL HOLDINGS — MAX 3 COINS", 14f), marginParams(0, 16, 0, 4))
        val coinSpinners = mutableListOf<Spinner>(); val amounts = mutableListOf<EditText>()
        repeat(3) { index ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val coin = spinner(MireiForegroundService.SUPPORTED_MARKETS); val amount = moneyEdit(if (index == 0) "150000" else "0")
            coinSpinners += coin; amounts += amount
            row.addView(coin, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.1f)); row.addView(amount, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.9f)); root.addView(row)
        }
        root.addView(title("RISK PROFILE", 14f), marginParams(0, 14, 0, 3))
        val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY"); val modeSpinner = spinner(modes); root.addView(modeSpinner)
        val manual = CheckBox(this).apply { text = "Manual TP/SL — locks profile" }; root.addView(manual)
        val sl = percentEdit("0.50"); val tp = percentEdit("1.00")
        root.addView(title("Stop Loss %", 12f)); root.addView(sl); root.addView(title("Take Profit %", 12f)); root.addView(tp)
        root.addView(title("Total ≤ Rp 150.000. These amounts are your existing paper holdings, not bot BUY orders.", 12f), marginParams(0, 7, 0, 0))
        sl.isEnabled = false; tp.isEnabled = false; manual.setOnCheckedChangeListener { _, checked -> modeSpinner.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        AlertDialog.Builder(this).setTitle("START PAPER RUNTIME").setView(root).setNegativeButton("CANCEL", null).setPositiveButton("START") { _, _ ->
            val allocations = parseAllocations(coinSpinners, amounts)
            val total = allocations.values.sum()
            if (allocations.isEmpty() || allocations.size > 3 || total > 150000.0001) { showMessage("Invalid portfolio", "Use 1–3 coins and keep total allocation at or below Rp 150.000."); return@setPositiveButton }
            if (manual.isChecked) {
                val slValue = sl.text.toString().replace(",", ".").toDoubleOrNull(); val tpValue = tp.text.toString().replace(",", ".").toDoubleOrNull()
                if (slValue == null || tpValue == null || slValue <= 0.0 || tpValue <= slValue) { showMessage("Invalid TP/SL", "Take Profit must be greater than Stop Loss."); return@setPositiveButton }
            }
            val selectedExchange = MireiForegroundService.SUPPORTED_EXCHANGES[exchangeSpinner.selectedItemPosition]
            if (selectedExchange != MireiForegroundService.DEFAULT_EXCHANGE) { showMessage("Exchange adapter not active", "${exchangeLabel(selectedExchange)} is registered as an exchange/API target using Freqtrade-style naming, but this Android paper build currently executes against INDODAX public market data."); return@setPositiveButton }
            persistRisk(modeSpinner.selectedItem.toString(), manual.isChecked, sl.text.toString(), tp.text.toString())
            val raw = allocations.entries.joinToString(";") { "${it.key}=${it.value}" }
            startRuntime(raw, allocations.keys.first(), selectedExchange)
        }.show()
    }

    private fun startRuntime(raw: String, primary: String, exchange: String) {
        val intent = Intent(this, MireiForegroundService::class.java).setAction(MireiForegroundService.ACTION_START).apply { putExtra(MireiForegroundService.EXTRA_SYMBOL, primary); putExtra(MireiForegroundService.EXTRA_EXCHANGE, exchange); putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, raw) }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
        buildRunningScreen()
    }

    private fun parseAllocations(coins: List<Spinner>, amounts: List<EditText>): LinkedHashMap<String, Double> = linkedMapOf<String, Double>().apply {
        for (i in coins.indices) { val amount = amounts[i].text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; if (amount > 0.0) put(coins[i].selectedItem.toString(), amount) }
    }

    private fun showRiskDialog() {
        val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY")
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 6, 20, 4) }
        val mode = spinner(modes); mode.setSelection(max(0, modes.indexOf(prefs.getString(KEY_MODE, "BALANCED")))); root.addView(title("Risk profile", 14f)); root.addView(mode)
        val manual = CheckBox(this).apply { text = "Manual TP/SL — locks profile" }; root.addView(manual)
        val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.50") ?: "0.50"); val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "1.00") ?: "1.00")
        root.addView(title("Stop Loss %", 12f)); root.addView(sl); root.addView(title("Take Profit %", 12f)); root.addView(tp)
        manual.isChecked = prefs.getBoolean(KEY_MANUAL, false); mode.isEnabled = !manual.isChecked; sl.isEnabled = manual.isChecked; tp.isEnabled = manual.isChecked
        manual.setOnCheckedChangeListener { _, checked -> mode.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        AlertDialog.Builder(this).setTitle("AI RISK & EXIT PROFILE").setView(root).setNegativeButton("CANCEL", null).setPositiveButton("SAVE") { _, _ ->
            val slValue = sl.text.toString().replace(",", ".").toDoubleOrNull(); val tpValue = tp.text.toString().replace(",", ".").toDoubleOrNull()
            if (manual.isChecked && (slValue == null || tpValue == null || slValue <= 0.0 || tpValue <= slValue)) { showMessage("Invalid TP/SL", "Take Profit must be greater than Stop Loss."); return@setPositiveButton }
            persistRisk(mode.selectedItem.toString(), manual.isChecked, slValue?.toString() ?: "0.50", tpValue?.toString() ?: "1.00")
            sendSimpleAction(MireiForegroundService.ACTION_APPLY_RISK)
        }.show()
    }

    private fun persistRisk(mode: String, manual: Boolean, sl: String, tp: String) { prefs.edit().putString(KEY_MODE, mode).putBoolean(KEY_MANUAL, manual).putString(KEY_MANUAL_SL, sl).putString(KEY_MANUAL_TP, tp).apply() }
    private fun spinner(values: List<String>) = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, values) }
    private fun moneyEdit(value: String) = EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; hint = "Rp"; setText(value) }
    private fun percentEdit(value: String) = EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(value) }
    private fun exchangeLabel(id: String): String = when (id) { "indodax" -> "indodax — ACTIVE"; else -> "$id — API CATALOG" }
    private fun sendSimpleAction(action: String) { val intent = Intent(this, MireiForegroundService::class.java).setAction(action); if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent) }

    private fun renderStatus(intent: Intent) {
        val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "UNKNOWN"
        if (state == "RUNNING" && !screenRunning) buildRunningScreen()
        if (state == "STOP" && screenRunning) buildStopScreen()
        val symbol = intent.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: MireiForegroundService.DEFAULT_SYMBOL; val exchange = intent.getStringExtra(MireiForegroundService.EXTRA_EXCHANGE) ?: MireiForegroundService.DEFAULT_EXCHANGE
        val price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0); val bid = intent.getDoubleExtra(MireiForegroundService.EXTRA_BID, 0.0); val ask = intent.getDoubleExtra(MireiForegroundService.EXTRA_ASK, 0.0); val high = intent.getDoubleExtra(MireiForegroundService.EXTRA_HIGH_24H, 0.0); val low = intent.getDoubleExtra(MireiForegroundService.EXTRA_LOW_24H, 0.0); val volume = intent.getDoubleExtra(MireiForegroundService.EXTRA_VOLUME_24H, 0.0)
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0); val balance = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0); val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0); val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0); val confidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0)
        val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"; val rationale = intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE) ?: "no_decision"; val agents = intent.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty(); val reasons = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty()
        val momentum = intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0); val volatility = intent.getDoubleExtra(MireiForegroundService.EXTRA_VOLATILITY, 0.0); val sentiment = intent.getDoubleExtra(MireiForegroundService.EXTRA_SENTIMENT, 0.0); val forecast = intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0); val spread = intent.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0); val tickChange = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_TICK, 0.0); val change1m = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0); val change5m = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0); val change15m = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0); val flow = intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0); val trend = intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0); val trades = intent.getIntExtra(MireiForegroundService.EXTRA_TRADE_COUNT, 0); val buy = intent.getDoubleExtra(MireiForegroundService.EXTRA_BUY_VOLUME, 0.0); val sell = intent.getDoubleExtra(MireiForegroundService.EXTRA_SELL_VOLUME, 0.0)
        val lastTrade = intent.getLongExtra(MireiForegroundService.EXTRA_LAST_TRADE, 0L); val snap = intent.getLongExtra(MireiForegroundService.EXTRA_SNAPSHOT_TIME, 0L); val age = intent.getLongExtra(MireiForegroundService.EXTRA_SOURCE_AGE, 0L); val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false); val online = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false); val exchangeHealthy = intent.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false); val error = intent.getStringExtra(MireiForegroundService.EXTRA_ERROR); val positionsDetail = intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty(); val scanner = intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty()

        status.text = """
            STATE
            State: $state    Exchange: $exchange
            Execution: PAPER ONLY    Market: $symbol

            SYSTEM HEALTH
            ${if (fresh && online && exchangeHealthy && error.isNullOrBlank()) "HEALTHY" else "DEGRADED / SAFE HOLD"}
            Market ${if (fresh) "LIVE / FRESH" else "STALE / UNAVAILABLE"} · source age ${age}ms

            MARKET PULSE
            Price: ${numberFormat.format(price)}
            Bid/Ask: ${numberFormat.format(bid)} / ${numberFormat.format(ask)}   Spread: ${"%.4f".format(Locale.US, spread)}%
            24H H/L: ${numberFormat.format(high)} / ${numberFormat.format(low)}
            24H Volume: ${numberFormat.format(volume)}

            PRICE / MOMENTUM
            Tick: ${"%.4f".format(Locale.US, tickChange)}%   1m: ${"%.4f".format(Locale.US, change1m)}%   5m: ${"%.4f".format(Locale.US, change5m)}%   15m: ${"%.4f".format(Locale.US, change15m)}%
            Momentum: ${"%.4f".format(Locale.US, momentum)}%   Volatility: ${"%.4f".format(Locale.US, volatility)}%   Trend: ${"%.4f".format(Locale.US, trend)}%

            FLOW / SENTIMENT
            Trades: $trades   Buy volume: ${numberFormat.format(buy)}   Sell volume: ${numberFormat.format(sell)}
            Trade flow: ${"%.2f".format(Locale.US, flow)}%   Sentiment: ${"%.2f".format(Locale.US, sentiment)}   Forecast: ${"%.3f".format(Locale.US, forecast)}

            ACCOUNT / PORTFOLIO
            Equity: Rp ${numberFormat.format(equity)}   Available cash: Rp ${numberFormat.format(balance)}
            Daily PnL: Rp ${numberFormat.format(pnl)}   Open positions: $positions

            ACTIVE POSITIONS
            ${positionsDetail.ifBlank { "none" }}

            DECISION
            $action (${(confidence * 100).toInt()}%)
            Reason: $rationale
            Entry gates: ${reasons.ifBlank { "none" }}

            AGENTS
            ${agents.ifBlank { "not evaluated" }}

            MARKET SCANNER / VOLUME SHARE
            ${scanner.ifBlank { "refreshing..." }}

            DATA TIME
            Last trade: ${formatEpoch(lastTrade)}   Snapshot: ${formatEpoch(snap)}
            ${if (error.isNullOrBlank()) "" else "ERROR: $error"}
        """.trimIndent()
        if (price > 0.0) { priceSeries += price; while (priceSeries.size > 120) priceSeries.removeAt(0); if (::marketChart.isInitialized) marketChart.setValues(priceSeries) }
        refreshHistoryViews()
    }

    private fun refreshHistoryViews() {
        if (!::historyContainer.isInitialized) return
        historyContainer.removeAllViews()
        val db = MireiDatabase(this)
        historyContainer.addView(historySection("PAPER HISTORY — TRADES", tradesText(db.recentTrades(20))))
        historyContainer.addView(historySection("DECISION HISTORY — LATEST 30", decisionsText(db.recentSuggestions(30))))
    }

    private fun tradesText(rows: List<TradeRow>): String = if (rows.isEmpty()) "No trade history." else rows.joinToString("\n") { "${formatEpoch(it.closedAtEpochMs ?: it.openedAtEpochMs)} | ${it.symbol} | ${it.status} | Rp ${numberFormat.format(it.stakeIdr)} | entry ${numberFormat.format(it.entryPrice ?: 0.0)} | exit ${numberFormat.format(it.exitPrice ?: 0.0)} | PnL Rp ${numberFormat.format(it.pnlIdr)} | ${it.exitReason ?: "OPEN"}" }
    private fun decisionsText(rows: List<DecisionRow>): String = if (rows.isEmpty()) "No decision history." else rows.joinToString("\n") { "${formatEpoch(it.createdAtEpochMs)} | ${it.symbol} | ${it.action} ${(it.confidence * 100).toInt()}% | ${it.reason}" }
    private fun historySection(title: String, text: String): TextView = TextView(this).apply { this.text = "$title\n$text"; textSize = 12.5f; setPadding(10, 18, 10, 18) }

    private fun confirmDeleteHistory() {
        AlertDialog.Builder(this).setTitle("DELETE HISTORY?").setMessage("Closed trades and decision/audit history are removed. Open trade rows stay so an active paper position can still close safely.").setNegativeButton("CANCEL", null).setPositiveButton("DELETE") { _, _ -> sendSimpleAction(MireiForegroundService.ACTION_DELETE_HISTORY); refreshHistoryViews() }.show()
    }

    private fun showMessage(title: String, message: String) { AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("OK", null).show() }
    private fun formatEpoch(epochMs: Long): String = if (epochMs <= 0L) "n/a" else SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(Date(epochMs))
    private fun requestNotificationPermissionIfNeeded() { if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS) }

    class SparklineView(context: Context) : View(context) {
        private val values = mutableListOf<Double>(); private val paint = Paint(Paint.ANTI_ALIAS_FLAG); private val path = Path()
        fun setValues(newValues: List<Double>) { values.clear(); values.addAll(newValues); invalidate() }
        override fun onDraw(canvas: Canvas) { super.onDraw(canvas); if (values.size < 2) return; val minV = values.minOrNull() ?: 0.0; val maxV = values.maxOrNull() ?: minV; val span = max(1e-9, maxV - minV); path.reset(); values.forEachIndexed { i, v -> val x = i * width.toFloat() / (values.size - 1); val y = height - ((v - minV) / span * height); if (i == 0) path.moveTo(x, y.toFloat()) else path.lineTo(x, y.toFloat()) }; paint.style = Paint.Style.STROKE; paint.strokeWidth = 4f; paint.color = 0xff22ccaa.toInt(); canvas.drawPath(path, paint) }
    }

    companion object { private const val PREFS_NAME = "mirei_settings"; private const val KEY_MODE = "mode"; private const val KEY_MANUAL = "manual_risk"; private const val KEY_MANUAL_SL = "manual_sl"; private const val KEY_MANUAL_TP = "manual_tp"; private const val REQUEST_NOTIFICATIONS = 2001 }
}
