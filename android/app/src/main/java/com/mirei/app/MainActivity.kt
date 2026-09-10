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
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TableLayout
import android.widget.TableRow
import android.widget.TextView
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max

class MainActivity : Activity() {
    private lateinit var root: LinearLayout
    private var running = false
    private var latestScanner = ""
    private var selectedPulse = MireiForegroundService.DEFAULT_SYMBOL
    private val priceSeries = mutableListOf<Double>()
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID"))
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, MODE_PRIVATE) }

    private val receiver = object : BroadcastReceiver() { override fun onReceive(context: Context?, intent: Intent?) { if (intent?.action == MireiForegroundService.ACTION_STATUS) render(intent) } }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState); numberFormat.maximumFractionDigits = 2; requestNotificationPermissionIfNeeded(); buildDashboard(false); requestRefresh()
    }
    override fun onStart() {
        super.onStart(); val filter = IntentFilter(MireiForegroundService.ACTION_STATUS); if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED) else registerReceiver(receiver, filter); requestRefresh()
    }
    override fun onStop() { runCatching { unregisterReceiver(receiver) }; super.onStop() }

    private fun buildDashboard(isRunning: Boolean) {
        running = isRunning
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 24, 18, 28) }
        root.addView(text("Mirei ミレイ", 29f, true)); root.addView(text("Android-first · dynamic paper trading", 14f, false), margin(0, 2, 0, 12)); root.addView(cardView("RUNTIME", text(if (isRunning) "RUNNING · PAPER ONLY" else "STOPPED · PAPER ONLY", 18f, true)))
        root.addView(section("MARKET PULSE"))
        val pulseSelector = spinner(MireiForegroundService.SUPPORTED_MARKETS).apply { setSelection(max(0, MireiForegroundService.SUPPORTED_MARKETS.indexOf(selectedPulse))); onItemSelectedListener = SimpleItemSelectedListener { selectedPulse = it; renderPulseFromScanner() } }
        root.addView(rowLabel("Selected coin", pulseSelector), margin(0, 0, 0, 6)); root.addView(pulseCard("Waiting for market data…"))
        root.addView(section("MARKET SCANNER · VOLUME SHARE")); root.addView(scannerTable("No scanner snapshot yet. Press REFRESH DATA."))
        if (isRunning) {
            root.addView(section("DECISION COUNTS")); root.addView(countCards()); root.addView(section("MARKET / PRICE GRAPH")); root.addView(cardView("LIVE PRICE", SparklineView(this).also { it.tag = "chart" }, 210)); root.addView(section("ACCOUNT / PORTFOLIO")); root.addView(text("Waiting for portfolio…", 14f, false).apply { tag = "portfolioSummary"; setPadding(10, 10, 10, 10); background = panel() }); root.addView(section("ACTIVE POSITIONS · IDR PRICE PER COIN")); root.addView(text("Waiting for positions…", 14f, false).apply { tag = "positions"; setPadding(10, 10, 10, 10); background = panel() }); root.addView(section("LATEST DECISION")); root.addView(decisionCard()); root.addView(section("AGENTS · SEPARATED BY COIN")); root.addView(agentContainer()); root.addView(section("HISTORY · READABLE TABLES")); root.addView(historyView())
        } else {
            root.addView(section("START PAPER PORTFOLIO")); root.addView(cardView("INITIAL CAPITAL", text("Rp 150.000 is the portfolio value you already bought. START records existing coin allocations; it does not create a BUY order.", 14f, false)))
        }
        root.addView(section("CONTROLS"))
        if (isRunning) { root.addView(actionButton("RISK / EXIT SETTINGS") { showRiskDialog() }); root.addView(actionButton("REFRESH DATA") { requestRefresh() }); root.addView(actionButton("HOLD") { send(MireiForegroundService.ACTION_HOLD) }); root.addView(actionButton("CLOSE ALL") { send(MireiForegroundService.ACTION_CLOSE_ALL) }); root.addView(actionButton("STOP") { send(MireiForegroundService.ACTION_STOP) }) }
        else { root.addView(actionButton("START") { showStartDialog() }); root.addView(actionButton("REFRESH DATA") { requestRefresh() }) }
        root.addView(actionButton("DELETE HISTORY") { confirmDeleteHistory() }); setContentView(ScrollView(this).apply { isFillViewport = true; addView(root, ViewGroup.LayoutParams(-1, -2)) })
    }

    private fun render(intent: Intent) {
        val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP"
        if (state == "RUNNING" && !running) { buildDashboard(true); return }
        if (state == "STOP" && running) { buildDashboard(false); return }
        latestScanner = intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty(); val price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0); if (price > 0.0) { priceSeries += price; while (priceSeries.size > 120) priceSeries.removeAt(0) }
        renderPulseFromScanner(); replaceScannerTable(); if (!running) return
        root.findViewWithTag<SparklineView>("chart")?.setValues(priceSeries)
        val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"; val confidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0); val reason = intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE) ?: "no_decision"; val gates = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty()
        root.findViewWithTag<TextView>("portfolioSummary")?.text = portfolioText(intent); root.findViewWithTag<TextView>("positions")?.text = positionsText(intent); root.findViewWithTag<TextView>("decision")?.text = decisionText(intent, action, confidence, reason, gates); refreshDynamicTables(intent)
    }

    private fun replaceScannerTable() { val old = root.findViewWithTag<View>("scanner") ?: return; replaceChild(old, scannerTable(latestScanner)) }
    private fun refreshDynamicTables(intent: Intent) {
        val counts = root.findViewWithTag<LinearLayout>("counts"); if (counts != null) counts.parent?.let { replaceChild(counts, countCards()) }
        root.findViewWithTag<LinearLayout>("agentsContainer")?.let { container -> container.removeAllViews(); val summary = intent.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty(); summary.split("\n\n").filter { it.isNotBlank() }.forEach { block -> val coin = block.substringBefore(" =>").trim(); val body = block.substringAfter("=>", "").trim(); container.addView(cardView(coin, text(formatAgentBlock(body), 13.5f, false)), margin(0, 0, 0, 8)) }; if (container.childCount == 0) container.addView(text("No agent evaluation yet.", 14f, false)) }
        refreshHistory()
    }

    private fun renderPulseFromScanner() {
        val row = latestScanner.lines().mapNotNull { parseScanner(it) }.firstOrNull { it.coin == selectedPulse } ?: latestScanner.lines().mapNotNull { parseScanner(it) }.firstOrNull()
        val value = if (row == null) "No snapshot yet. Tap REFRESH DATA." else """${row.coin}\nPrice: Rp ${numberFormat.format(row.price)}\n1m change: ${fmt(row.change1m)}%    Momentum: ${fmt(row.momentum)}%\nTrend: ${fmt(row.trend)}%        Volume share: ${fmt(row.volumeShare)}%""".trimIndent()
        root.findViewWithTag<View>("pulse")?.let { replaceChild(it, pulseCard(value)) }
    }
    private fun parseScanner(line: String): ScannerRow? { val p = line.split('|'); if (p.size < 6) return null; return runCatching { ScannerRow(p[0], p[1].toDouble(), p[2].toDouble(), p[3].toDouble(), p[4].toDouble(), p[5].toDouble()) }.getOrNull() }
    private fun scannerTable(raw: String): View { val table = TableLayout(this).apply { isStretchAllColumns = false; tag = "scannerTable" }; table.addView(tableRow(listOf("COIN", "PRICE IDR", "1M %", "MOM %", "TREND %", "VOL SHARE %"), true)); raw.lines().mapNotNull { parseScanner(it) }.take(10).forEach { r -> table.addView(tableRow(listOf(r.coin, numberFormat.format(r.price), fmt(r.change1m), fmt(r.momentum), fmt(r.trend), fmt(r.volumeShare)), false)) }; return HorizontalScrollView(this).apply { tag = "scanner"; addView(table, ViewGroup.LayoutParams(-2, -2)) } }

    private fun countCards(): LinearLayout { val rows = MireiDatabase(this).recentSuggestions(200); val buy = rows.count { it.action == "BUY" }; val sell = rows.count { it.action == "SELL" }; val hold = rows.count { it.action == "HOLD" }; return LinearLayout(this).apply { tag = "counts"; orientation = LinearLayout.HORIZONTAL; addView(metric("BUY", buy), LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = 5 }); addView(metric("SELL", sell), LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = 5; rightMargin = 5 }); addView(metric("HOLD", hold), LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = 5 }) } }
    private fun metric(label: String, value: Int): TextView = text("$label\n$value", 22f, true).apply { gravity = Gravity.CENTER; setPadding(10, 16, 10, 16); background = panel() }
    private fun portfolioText(intent: Intent): String { val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0); val cash = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0); val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0); val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0); return "Equity: Rp ${numberFormat.format(equity)}\nAvailable cash: Rp ${numberFormat.format(cash)}\nRealized daily PnL: Rp ${numberFormat.format(pnl)}\nOpen positions: $positions\n\nINPUT → OUTPUT\n${intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty().ifBlank { "No active portfolio rows." }}" }
    private fun positionsText(intent: Intent): String { val raw = intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty(); if (raw.isBlank()) return "No active positions."; val table = StringBuilder("Price unit = IDR per 1 coin. Stake, value and PnL = IDR.\n\n"); raw.lines().forEach { line -> val map = line.split('|').mapNotNull { token -> token.split('=', limit = 2).takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap(); if (map.isNotEmpty()) table.append("${line.substringBefore('|')}\nStake Rp ${map["stake"] ?: "0"}\nEntry Rp ${map["entry"] ?: "0"} → Current Rp ${map["current"] ?: "0"}\nValue Rp ${map["value"] ?: "0"} · Unrealized PnL Rp ${map["unrealized"] ?: "0"}\nTP Rp ${map["tp"] ?: "0"} (+${map["tp_pct"] ?: "0"}%) · SL Rp ${map["sl"] ?: "0"} (-${map["sl_pct"] ?: "0"}%)\n\n") }; return table.toString().trim() }
    private fun decisionText(intent: Intent, action: String, confidence: Double, reason: String, gates: String): String { val momentum = intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0); val forecast = intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0); val flow = intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0); val trend = intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0); return "ACTION: $action · ${(confidence * 100).toInt()}%\n\nWhy: ${humanReason(reason)}\n\nGates: ${gates.ifBlank { "none" }}\n\nEvidence\nMomentum ${fmt(momentum)}% · Trend ${fmt(trend)}% · Flow ${fmt(flow)}% · Forecast ${(forecast * 100).toInt()}%\n\nTap this card for detail." }
    private fun decisionCard(): TextView = text("Waiting for decision…", 15f, false).apply { tag = "decision"; setPadding(16, 16, 16, 16); background = panel(); setOnClickListener { AlertDialog.Builder(this@MainActivity).setTitle("MIREI DECISION DETAIL").setMessage(text).setPositiveButton("OK", null).show() } }
    private fun agentContainer(): LinearLayout = LinearLayout(this).apply { tag = "agentsContainer"; orientation = LinearLayout.VERTICAL; addView(text("Waiting for agent evaluation…", 14f, false)) }
    private fun formatAgentBlock(body: String): String = body.replace(" | ", "\n").replace("CANDLE:", "CANDLE  · ").replace("MARKET:", "MARKET  · ").replace("SENTIMENT:", "SENTIMENT  · ").replace("FORECAST:", "FORECAST  · ")
    private fun historyView(): LinearLayout = LinearLayout(this).apply { tag = "history"; orientation = LinearLayout.VERTICAL; addView(historyMatrix()); addView(sectionText("TRADE LEDGER")); addView(tradeTable()) }
    private fun refreshHistory() { root.findViewWithTag<LinearLayout>("history")?.let { h -> h.removeAllViews(); h.addView(historyMatrix()); h.addView(sectionText("TRADE LEDGER")); h.addView(tradeTable()) } }
    private fun historyMatrix(): View { val rows = MireiDatabase(this).recentSuggestions(60); val symbols = rows.map { it.symbol }.distinct().take(3); if (symbols.isEmpty()) return sectionText("No decision history yet."); val table = TableLayout(this).apply { isStretchAllColumns = false }; table.addView(tableRow(listOf("TIME") + symbols, true)); rows.groupBy { it.createdAtEpochMs }.entries.take(20).forEach { (time, decisions) -> val cells = symbols.map { symbol -> decisions.firstOrNull { it.symbol == symbol }?.let { "${it.action} ${(it.confidence * 100).toInt()}%" } ?: "—" }; table.addView(tableRow(listOf(formatEpoch(time)) + cells, false)) }; return HorizontalScrollView(this).apply { addView(table, ViewGroup.LayoutParams(-2, -2)) } }
    private fun tradeTable(): View { val rows = MireiDatabase(this).recentTrades(30); if (rows.isEmpty()) return sectionText("No trades recorded."); val table = TableLayout(this).apply { isStretchAllColumns = false }; table.addView(tableRow(listOf("TIME", "COIN", "TYPE", "STAKE IDR", "ENTRY IDR", "EXIT IDR", "PnL IDR", "STATUS"), true)); rows.forEach { r -> table.addView(tableRow(listOf(formatEpoch(r.closedAtEpochMs ?: r.openedAtEpochMs), r.symbol, r.side, numberFormat.format(r.stakeIdr), numberFormat.format(r.entryPrice ?: 0.0), numberFormat.format(r.exitPrice ?: 0.0), numberFormat.format(r.pnlIdr), r.status), false)) }; return HorizontalScrollView(this).apply { addView(table, ViewGroup.LayoutParams(-2, -2)) } }
    private fun tableRow(values: List<String>, header: Boolean): TableRow = TableRow(this).apply { values.forEach { value -> addView(text(value, if (header) 11.5f else 11f, header).apply { setPadding(10, 9, 10, 9); minWidth = 88; if (header) background = panel() }) } }

    private fun showStartDialog() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 6, 18, 4) }; root.addView(text("EXCHANGE", 13f, true)); val exchange = spinner(MireiForegroundService.SUPPORTED_EXCHANGES.map { if (it == "indodax") "$it — ACTIVE" else "$it — API CATALOG" }); root.addView(exchange); root.addView(text("INITIAL HOLDINGS · 1–3 COINS", 13f, true), margin(0, 14, 0, 4)); val coins = mutableListOf<Spinner>(); val amounts = mutableListOf<EditText>()
        repeat(3) { val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }; val coin = spinner(MireiForegroundService.SUPPORTED_MARKETS); val amount = moneyEdit("0"); coins += coin; amounts += amount; row.addView(coin, LinearLayout.LayoutParams(0, -2, 1.2f)); row.addView(amount, LinearLayout.LayoutParams(0, -2, 0.8f)); root.addView(row) }
        root.addView(text("RISK PROFILE", 13f, true), margin(0, 12, 0, 3)); val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY"); val mode = spinner(modes); root.addView(mode); val manual = CheckBox(this).apply { text = "Manual TP/SL · locks risk profile" }; root.addView(manual); val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.25") ?: "0.25"); val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "0.60") ?: "0.60"); root.addView(text("Stop Loss %", 12f, false)); root.addView(sl); root.addView(text("Take Profit %", 12f, false)); root.addView(tp); sl.isEnabled = false; tp.isEnabled = false; manual.setOnCheckedChangeListener { _, checked -> mode.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        AlertDialog.Builder(this).setTitle("START PAPER PORTFOLIO").setView(root).setNegativeButton("CANCEL", null).setPositiveButton("START") { _, _ ->
            val allocations = linkedMapOf<String, Double>(); for (i in coins.indices) { val amount = amounts[i].text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; if (amount > 0) allocations[coins[i].selectedItem.toString()] = amount }; val total = allocations.values.sum(); if (allocations.isEmpty() || allocations.size > 3 || total <= 0 || total > 150000.0001) { showMessage("Invalid portfolio", "Allocate 1–3 existing holdings, total ≤ Rp 150.000."); return@setPositiveButton }
            val selectedExchange = MireiForegroundService.SUPPORTED_EXCHANGES[exchange.selectedItemPosition]; if (selectedExchange != MireiForegroundService.DEFAULT_EXCHANGE) { showMessage("Adapter not active", "Only INDODAX public market data is active in this Android paper runtime."); return@setPositiveButton }
            val manualSl = sl.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; val manualTp = tp.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; if (manual.isChecked && (manualSl <= 0 || manualTp <= manualSl)) { showMessage("Invalid TP/SL", "TP must be greater than SL."); return@setPositiveButton }
            prefs.edit().putString(KEY_MODE, mode.selectedItem.toString()).putBoolean(KEY_MANUAL, manual.isChecked).putString(KEY_MANUAL_SL, manualSl.toString()).putString(KEY_MANUAL_TP, manualTp.toString()).apply(); startRuntime(allocations.entries.joinToString(";") { "${it.key}=${it.value}" }, allocations.keys.first(), selectedExchange)
        }.show()
    }

    private fun showRiskDialog() {
        val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY"); val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 6, 18, 4) }; val mode = spinner(modes); mode.setSelection(max(0, modes.indexOf(prefs.getString(KEY_MODE, "BALANCED")))); root.addView(text("Risk profile", 13f, true)); root.addView(mode); val manual = CheckBox(this).apply { text = "Manual TP/SL · locks risk profile" }; root.addView(manual); val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.25") ?: "0.25"); val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "0.60") ?: "0.60"); root.addView(text("Stop Loss %", 12f, false)); root.addView(sl); root.addView(text("Take Profit %", 12f, false)); root.addView(tp); manual.isChecked = prefs.getBoolean(KEY_MANUAL, false); mode.isEnabled = !manual.isChecked; sl.isEnabled = manual.isChecked; tp.isEnabled = manual.isChecked; manual.setOnCheckedChangeListener { _, checked -> mode.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        AlertDialog.Builder(this).setTitle("AI RISK / EXIT SETTINGS").setView(root).setNegativeButton("CANCEL", null).setPositiveButton("SAVE") { _, _ -> val s = sl.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; val t = tp.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; if (manual.isChecked && (s <= 0 || t <= s)) { showMessage("Invalid TP/SL", "TP must be greater than SL."); return@setPositiveButton }; prefs.edit().putString(KEY_MODE, mode.selectedItem.toString()).putBoolean(KEY_MANUAL, manual.isChecked).putString(KEY_MANUAL_SL, s.toString()).putString(KEY_MANUAL_TP, t.toString()).apply(); send(MireiForegroundService.ACTION_APPLY_RISK) }.show()
    }

    private fun startRuntime(raw: String, primary: String, exchange: String) { send(MireiForegroundService.ACTION_START, Intent(this, MireiForegroundService::class.java).setAction(MireiForegroundService.ACTION_START).apply { putExtra(MireiForegroundService.EXTRA_SYMBOL, primary); putExtra(MireiForegroundService.EXTRA_EXCHANGE, exchange); putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, raw) }); buildDashboard(true) }
    private fun requestRefresh() = send(MireiForegroundService.ACTION_REFRESH)
    private fun send(action: String, intent: Intent = Intent(this, MireiForegroundService::class.java).setAction(action)) { if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent) }
    private fun confirmDeleteHistory() { AlertDialog.Builder(this).setTitle("DELETE HISTORY?").setMessage("Closed trades, decisions and audit logs will be deleted. Open positions remain so active paper risk is not corrupted.").setNegativeButton("CANCEL", null).setPositiveButton("DELETE") { _, _ -> send(MireiForegroundService.ACTION_DELETE_HISTORY); refreshHistory() }.show() }
    private fun showMessage(title: String, message: String) { AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("OK", null).show() }
    private fun text(value: String, size: Float, bold: Boolean): TextView = TextView(this).apply { text = value; textSize = size; if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setTextColor(0xffeeeeee.toInt()) }
    private fun section(value: String): TextView = text(value, 13f, true).apply { setPadding(2, 18, 2, 8) }
    private fun sectionText(value: String): TextView = text(value, 13f, false).apply { setPadding(10, 12, 10, 12) }
    private fun cardView(label: String, child: View, height: Int? = null): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(14, 12, 14, 12); background = panel(); addView(text(label, 11f, true)); addView(child, margin(0, 8, 0, 0)); if (height != null) child.layoutParams = LinearLayout.LayoutParams(-1, height) }
    private fun pulseCard(value: String): TextView = text(value, 14f, false).apply { tag = "pulse"; setPadding(16, 16, 16, 16); background = panel() }
    private fun rowLabel(label: String, view: View): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; addView(text(label, 11f, true)); addView(view) }
    private fun actionButton(label: String, action: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { action() }; isAllCaps = false }
    private fun spinner(values: List<String>): Spinner = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, values) }
    private fun moneyEdit(value: String): EditText = EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(value) }
    private fun percentEdit(value: String): EditText = moneyEdit(value)
    private fun margin(l: Int, t: Int, r: Int, b: Int) = LinearLayout.LayoutParams(-1, -2).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }
    private fun panel() = GradientDrawable().apply { cornerRadius = 18f; setColor(0xff18222b.toInt()); setStroke(1, 0xff33424d.toInt()) }
    private fun fmt(v: Double) = "%.3f".format(Locale.US, v)
    private fun formatEpoch(ms: Long) = if (ms <= 0) "n/a" else SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(Date(ms))
    private fun humanReason(reason: String): String = when (reason) { "agent_conflict_requires_human_decision" -> "Agents disagree; Suggestion mode requires human confirmation."; "agent_consensus_or_take_over" -> "Agents are not aligned for automatic entry."; "forecast_confidence_low" -> "Forecast confidence is below the entry threshold."; "momentum_not_positive" -> "Short-term momentum is not positive enough for entry."; "position_limit" -> "Maximum open positions are already reached."; else -> reason.replace('_', ' ') }
    private fun replaceChild(old: View, replacement: View) { val parent = old.parent as? ViewGroup ?: return; val index = parent.indexOfChild(old); parent.removeViewAt(index); parent.addView(replacement, index) }
    private fun requestNotificationPermissionIfNeeded() { if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS) }
    class SparklineView(context: Context) : View(context) { private val values = mutableListOf<Double>(); private val paint = Paint(Paint.ANTI_ALIAS_FLAG); private val path = Path(); fun setValues(input: List<Double>) { values.clear(); values.addAll(input); invalidate() }; override fun onDraw(canvas: Canvas) { super.onDraw(canvas); if (values.size < 2) return; val min = values.minOrNull() ?: 0.0; val max = values.maxOrNull() ?: min; val span = max(1e-9, max - min); path.reset(); values.forEachIndexed { i, v -> val x = i * width.toFloat() / (values.size - 1); val y = height - ((v - min) / span * height); if (i == 0) path.moveTo(x, y.toFloat()) else path.lineTo(x, y.toFloat()) }; paint.style = Paint.Style.STROKE; paint.strokeWidth = 4f; paint.color = 0xff22ccaa.toInt(); canvas.drawPath(path, paint) } }
    data class ScannerRow(val coin: String, val price: Double, val change1m: Double, val momentum: Double, val trend: Double, val volumeShare: Double)
    class SimpleItemSelectedListener(private val onSelected: (String) -> Unit) : AdapterView.OnItemSelectedListener { override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) { onSelected(parent?.getItemAtPosition(position)?.toString().orEmpty()) }; override fun onNothingSelected(parent: AdapterView<*>?) = Unit }
    companion object { private const val PREFS_NAME = "mirei_settings"; private const val KEY_MODE = "mode"; private const val KEY_MANUAL = "manual_risk"; private const val KEY_MANUAL_SL = "manual_sl"; private const val KEY_MANUAL_TP = "manual_tp"; private const val REQUEST_NOTIFICATIONS = 2001 }
}
