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
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
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
import com.mirei.app.storage.DecisionRow
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.TradeRow
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var root: LinearLayout
    private lateinit var runtimeCard: TextView
    private lateinit var pulseHolder: LinearLayout
    private lateinit var scannerHolder: LinearLayout
    private lateinit var countHolder: LinearLayout
    private lateinit var chart: SparklineView
    private lateinit var portfolioHolder: LinearLayout
    private lateinit var positionsHolder: LinearLayout
    private lateinit var decisionHolder: LinearLayout
    private lateinit var agentsHolder: LinearLayout
    private lateinit var historyHolder: LinearLayout
    private lateinit var startButton: Button
    private lateinit var riskButton: Button
    private lateinit var refreshButton: Button
    private lateinit var holdButton: Button
    private lateinit var closeAllButton: Button
    private lateinit var stopButton: Button
    private lateinit var deleteButton: Button
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, MODE_PRIVATE) }
    private val priceSeries = mutableListOf<Double>()
    private var currentState = "STOP"
    private var scannerRaw = ""
    private var selectedPulse = MireiForegroundService.DEFAULT_SYMBOL

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == MireiForegroundService.ACTION_STATUS) render(intent)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        buildDashboard()
        requestRefresh()
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(MireiForegroundService.ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED) else registerReceiver(receiver, filter)
        // Pull the live service state whenever the Activity returns to the foreground.
        requestRefresh()
    }

    override fun onStop() {
        runCatching { unregisterReceiver(receiver) }
        super.onStop()
    }

    private fun buildDashboard() {
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(16, 20, 16, 28)
        }
        root.addView(text("Mirei ミレイ", 30f, true))
        root.addView(text("Android-first · paper trading dinamis", 14f, false), margin(0, 2, 0, 12))

        runtimeCard = text("BERHENTI · PAPER ONLY", 20f, true).apply { setPadding(16, 16, 16, 16); background = panel() }
        root.addView(cardView("RUNTIME", runtimeCard), margin(0, 0, 0, 4))

        addSection("KONTROL")
        startButton = actionButton("MULAI") { showStartDialog() }
        riskButton = actionButton("PENGATURAN RISIKO / TP-SL") { showRiskDialog() }
        refreshButton = actionButton("REFRESH DATA") { requestRefresh() }
        holdButton = actionButton("HOLD") { send(MireiForegroundService.ACTION_HOLD) }
        closeAllButton = actionButton("TUTUP SEMUA POSISI") { send(MireiForegroundService.ACTION_CLOSE_ALL) }
        stopButton = actionButton("STOP / JEDA") { send(MireiForegroundService.ACTION_STOP) }
        deleteButton = actionButton("HAPUS HISTORY") { confirmDeleteHistory() }
        root.addView(startButton)
        root.addView(riskButton)
        root.addView(refreshButton)
        root.addView(holdButton)
        root.addView(closeAllButton)
        root.addView(stopButton)
        root.addView(deleteButton)

        addSection("MARKET PULSE · 1 COIN")
        val pulseSelector = spinner(MireiForegroundService.SUPPORTED_MARKETS).apply {
            val idx = MireiForegroundService.SUPPORTED_MARKETS.indexOf(selectedPulse)
            if (idx >= 0) setSelection(idx)
            onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                    selectedPulse = MireiForegroundService.SUPPORTED_MARKETS[position]
                    renderPulse()
                }
                override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            }
        }
        root.addView(text("Pilih coin untuk grafik/telemetri utama", 11f, true), margin(0, 0, 0, 2))
        root.addView(pulseSelector)
        pulseHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(pulseHolder, margin(0, 4, 0, 0))

        addSection("MARKET SCANNER · VOLUME SHARE")
        scannerHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(scannerHolder)

        addSection("JUMLAH KEPUTUSAN")
        countHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(countHolder)

        addSection("GRAFIK HARGA")
        chart = SparklineView(this)
        root.addView(cardView("LIVE PRICE", chart, 220))

        addSection("AKUN / PORTOFOLIO")
        portfolioHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(portfolioHolder)

        addSection("POSISI AKTIF · HARGA IDR PER COIN")
        positionsHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(positionsHolder)

        addSection("KEPUTUSAN TERAKHIR · MENGAPA?")
        decisionHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(decisionHolder)

        addSection("AGENT · DIPISAH PER COIN")
        agentsHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(agentsHolder)

        addSection("HISTORY · TABEL YANG DAPAT DIBACA")
        historyHolder = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(historyHolder)

        setContentView(ScrollView(this).apply {
            isFillViewport = true
            addView(root, ViewGroup.LayoutParams(-1, -2))
        })
        renderEmptyState()
    }

    private fun render(intent: Intent) {
        currentState = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP"
        updateControls()
        runtimeCard.text = when (currentState) {
            "RUNNING" -> "BERJALAN · PAPER ONLY"
            "HOLD" -> "HOLD · PAPER ONLY"
            else -> "BERHENTI · PAPER ONLY"
        }

        scannerRaw = intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty()
        val selectedPrice = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0)
        if (selectedPrice > 0.0) {
            priceSeries += selectedPrice
            while (priceSeries.size > 120) priceSeries.removeAt(0)
            chart.setValues(priceSeries)
        }
        renderPulse()
        renderScanner()
        renderCounts()
        renderPortfolio(intent)
        renderPositions(intent)
        renderDecision(intent)
        renderAgents(intent)
        renderHistory()
    }

    private fun renderEmptyState() {
        pulseHolder.removeAllViews(); pulseHolder.addView(cardText("Belum ada snapshot pasar. Tekan REFRESH DATA."))
        scannerHolder.removeAllViews(); scannerHolder.addView(cardText("Scanner akan mengisi data publik setelah refresh."))
        countHolder.removeAllViews(); countHolder.addView(countCards(0, 0, 0))
        portfolioHolder.removeAllViews(); portfolioHolder.addView(cardText("Belum ada portfolio aktif."))
        positionsHolder.removeAllViews(); positionsHolder.addView(cardText("Belum ada posisi aktif."))
        decisionHolder.removeAllViews(); decisionHolder.addView(cardText("Belum ada keputusan Mirei."))
        agentsHolder.removeAllViews(); agentsHolder.addView(cardText("Agent menunggu data pasar."))
        historyHolder.removeAllViews(); historyHolder.addView(cardText("Belum ada history."))
        updateControls()
    }

    private fun renderPulse() {
        val row = scannerRaw.lines().mapNotNull { parseScanner(it) }.firstOrNull { it.coin == selectedPulse }
            ?: scannerRaw.lines().mapNotNull { parseScanner(it) }.firstOrNull()
        pulseHolder.removeAllViews()
        if (row == null) {
            pulseHolder.addView(cardText("Belum ada snapshot market untuk $selectedPulse."))
            return
        }
        pulseHolder.addView(cardView(row.coin, text(
            "Harga terakhir\nRp ${numberFormat.format(row.price)}\n\n" +
                "Perubahan 1 menit\n${signed(row.change1m)}%\n\n" +
                "Momentum\n${signed(row.momentum)}%\n\n" +
                "Trend\n${signed(row.trend)}%\n\n" +
                "Porsi volume scanner\n${fmt(row.volumeShare)}%",
            14f, false
        )))
    }

    private fun renderScanner() {
        scannerHolder.removeAllViews()
        val rows = scannerRaw.lines().mapNotNull { parseScanner(it) }.take(10)
        if (rows.isEmpty()) { scannerHolder.addView(cardText("Belum ada data scanner.")); return }
        val table = TableLayout(this)
        table.addView(tableRow(listOf("COIN", "HARGA IDR", "1M %", "MOM %", "TREND %", "VOL %"), true))
        rows.forEach { r -> table.addView(tableRow(listOf(r.coin, numberFormat.format(r.price), signed(r.change1m), signed(r.momentum), signed(r.trend), fmt(r.volumeShare)), false)) }
        scannerHolder.addView(horizontal(table))
    }

    private fun renderCounts() {
        val decisions = MireiDatabase(this).recentSuggestions(200)
        val buy = decisions.count { it.action == "BUY" }
        val hold = decisions.count { it.action == "HOLD" }
        val closed = MireiDatabase(this).recentTrades(200).count { it.status == "CLOSED" }
        countHolder.removeAllViews(); countHolder.addView(countCards(buy, closed, hold))
    }

    private fun countCards(buy: Int, sell: Int, hold: Int): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(metricCard("BUY", buy), LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = 4 })
        addView(metricCard("SELL", sell), LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = 2; rightMargin = 2 })
        addView(metricCard("HOLD", hold), LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = 4 })
    }

    private fun renderPortfolio(intent: Intent) {
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val cash = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0)
        val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        portfolioHolder.removeAllViews()
        portfolioHolder.addView(cardText(
            "Nilai akun\nRp ${numberFormat.format(equity)}\n\n" +
                "Kas tersedia\nRp ${numberFormat.format(cash)}\n\n" +
                "PnL terealisasi hari ini\nRp ${signedMoney(pnl)}\n\n" +
                "Posisi terbuka\n$positions"
        ))
        val raw = intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty()
        val rows = raw.lines().mapNotNull { parsePosition(it) }
        portfolioHolder.addView(text("INPUT → OUTPUT MODAL", 12f, true), margin(0, 10, 0, 4))
        if (rows.isEmpty()) portfolioHolder.addView(cardText("Tidak ada input/output posisi aktif."))
        else {
            val table = TableLayout(this)
            table.addView(tableRow(listOf("COIN", "MODAL IDR", "ENTRY IDR", "CURRENT IDR", "NILAI IDR", "PnL IDR"), true))
            rows.forEach { r -> table.addView(tableRow(listOf(r.coin, numberFormat.format(r.stake), numberFormat.format(r.entry), numberFormat.format(r.current), numberFormat.format(r.value), signedMoney(r.unrealized)), false)) }
            portfolioHolder.addView(horizontal(table))
        }
    }

    private fun renderPositions(intent: Intent) {
        val raw = intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty()
        val rows = raw.lines().mapNotNull { parsePosition(it) }
        positionsHolder.removeAllViews()
        if (rows.isEmpty()) { positionsHolder.addView(cardText("Tidak ada posisi aktif.")); return }
        rows.forEach { r ->
            positionsHolder.addView(cardView(r.coin, text(
                "Satuan harga: IDR per 1 coin\n" +
                    "Modal: Rp ${numberFormat.format(r.stake)}\n" +
                    "Entry: Rp ${numberFormat.format(r.entry)}\n" +
                    "Harga sekarang: Rp ${numberFormat.format(r.current)}\n" +
                    "Nilai posisi: Rp ${numberFormat.format(r.value)}\n" +
                    "PnL belum terealisasi: Rp ${signedMoney(r.unrealized)}\n\n" +
                    "Take Profit: Rp ${numberFormat.format(r.tp)}  (+${fmt(r.tpPct)}%)\n" +
                    "Stop Loss: Rp ${numberFormat.format(r.sl)}  (-${fmt(r.slPct)}%)",
                13.5f, false
            )), margin(0, 0, 0, 8))
        }
    }

    private fun renderDecision(intent: Intent) {
        val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val confidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0)
        val reason = intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE) ?: "belum ada keputusan"
        val gates = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty()
        val momentum = intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0)
        val trend = intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0)
        val flow = intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0)
        val forecast = intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0)
        val executions = intent.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty()
        decisionHolder.removeAllViews()
        val card = cardText(
            "AKSI  $action · ${(confidence * 100).toInt()}%\n\n" +
                "Mengapa\n${humanReason(reason)}\n\n" +
                "Gate masuk\n${gates.ifBlank { "tidak ada" }}\n\n" +
                "Bukti market\nMomentum ${signed(momentum)}%\nTrend ${signed(trend)}%\nFlow ${signed(flow)}%\nForecast ${(forecast * 100).toInt()}%\n\n" +
                "Event execution terbaru\n${executions.ifBlank { "belum ada entry/exit" }}\n\n" +
                "Ketuk untuk detail lengkap"
        )
        card.setOnClickListener {
            AlertDialog.Builder(this)
                .setTitle("DETAIL KEPUTUSAN MIREI")
                .setMessage(card.text)
                .setPositiveButton("TUTUP", null)
                .show()
        }
        decisionHolder.addView(card)
    }

    private fun renderAgents(intent: Intent) {
        val raw = intent.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty()
        agentsHolder.removeAllViews()
        val blocks = raw.split("\n\n").filter { it.isNotBlank() }
        if (blocks.isEmpty()) { agentsHolder.addView(cardText("Belum ada evaluasi agent.")); return }
        blocks.forEach { block ->
            val coin = block.substringBefore(" =>").trim()
            val body = block.substringAfter("=>", "").trim()
            val lines = body.split(" | ").map { token -> token.replace(":", " · ").replace("_", " ") }
            val table = TableLayout(this)
            table.addView(tableRow(listOf("AGENT", "HASIL / ALASAN"), true))
            lines.forEach { line ->
                val idx = line.indexOf(" · ")
                if (idx > 0) table.addView(tableRow(listOf(line.substring(0, idx), line.substring(idx + 3)), false))
                else table.addView(tableRow(listOf("INFO", line), false))
            }
            agentsHolder.addView(cardView(coin, horizontal(table)), margin(0, 0, 0, 8))
        }
    }

    private fun renderHistory() {
        historyHolder.removeAllViews()
        val db = MireiDatabase(this)
        val decisions = db.recentSuggestions(90)
        val symbols = decisions.map { it.symbol }.distinct().take(3).ifEmpty { MireiForegroundService.SUPPORTED_MARKETS.take(3) }
        val matrix = TableLayout(this)
        matrix.addView(tableRow(listOf("WAKTU") + symbols, true))
        decisions.groupBy { it.createdAtEpochMs }.entries.take(20).forEach { (time, rows) ->
            val cells = symbols.map { symbol -> rows.firstOrNull { it.symbol == symbol }?.let { "${it.action} ${(it.confidence * 100).toInt()}%" } ?: "—" }
            matrix.addView(tableRow(listOf(formatEpoch(time)) + cells, false))
        }
        historyHolder.addView(horizontal(matrix))
        historyHolder.addView(text("TRADE LEDGER", 12f, true), margin(0, 12, 0, 4))
        val trades = db.recentTrades(30)
        val tradeTable = TableLayout(this)
        tradeTable.addView(tableRow(listOf("WAKTU", "COIN", "TIPE", "STAKE", "ENTRY", "EXIT", "PnL", "STATUS"), true))
        trades.forEach { r -> tradeTable.addView(tableRow(listOf(formatEpoch(r.closedAtEpochMs ?: r.openedAtEpochMs), r.symbol, if (r.side == "INITIAL_HOLDING") "HOLDING AWAL" else r.side, numberFormat.format(r.stakeIdr), numberFormat.format(r.entryPrice ?: 0.0), numberFormat.format(r.exitPrice ?: 0.0), signedMoney(r.pnlIdr), r.status), false)) }
        historyHolder.addView(horizontal(tradeTable))
    }

    private fun showStartDialog() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 4, 18, 4) }
        root.addView(text("EXCHANGE", 12f, true))
        val exchange = spinner(MireiForegroundService.SUPPORTED_EXCHANGES.map { if (it == MireiForegroundService.DEFAULT_EXCHANGE) "$it · AKTIF" else "$it · KATALOG API" })
        root.addView(exchange)
        root.addView(text("COIN AWAL · MAKS 3", 12f, true), margin(0, 12, 0, 3))
        val coins = mutableListOf<Spinner>(); val amounts = mutableListOf<EditText>()
        repeat(3) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val coin = spinner(MireiForegroundService.SUPPORTED_MARKETS)
            val amount = moneyEdit("0")
            coins += coin; amounts += amount
            row.addView(coin, LinearLayout.LayoutParams(0, -2, 1.15f))
            row.addView(amount, LinearLayout.LayoutParams(0, -2, 0.85f).apply { leftMargin = 8 })
            root.addView(row)
        }
        root.addView(text("Total alokasi harus ≤ Rp 150.000. Nilai ini adalah coin yang SUDAH Anda beli; Mirei tidak membuat BUY awal.", 11f, false), margin(0, 8, 0, 5))
        root.addView(text("RISK PROFILE", 12f, true))
        val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY")
        val mode = spinner(modes); root.addView(mode)
        val manual = CheckBox(this).apply { text = "TP/SL manual · kunci profile" }; root.addView(manual)
        val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.10") ?: "0.10")
        val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "0.35") ?: "0.35")
        root.addView(text("Stop Loss %", 11f, false)); root.addView(sl)
        root.addView(text("Take Profit %", 11f, false)); root.addView(tp)
        sl.isEnabled = false; tp.isEnabled = false
        manual.setOnCheckedChangeListener { _, checked -> mode.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        val dialog = AlertDialog.Builder(this).setTitle("MULAI PORTFOLIO PAPER").setView(root).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val allocations = linkedMapOf<String, Double>()
                for (i in coins.indices) {
                    val amount = amounts[i].text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
                    if (amount > 0.0) allocations[coins[i].selectedItem.toString()] = amount
                }
                val total = allocations.values.sum()
                val manualSl = sl.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
                val manualTp = tp.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
                val selectedExchange = MireiForegroundService.SUPPORTED_EXCHANGES[exchange.selectedItemPosition]
                when {
                    allocations.isEmpty() || total > 150000.0001 -> showMessage("ALOKASI TIDAK VALID", "Masukkan 1–3 coin dan total maksimal Rp 150.000.")
                    selectedExchange != MireiForegroundService.DEFAULT_EXCHANGE -> showMessage("EXCHANGE BELUM AKTIF", "Adapter paper Android yang aktif saat ini adalah INDODAX public market data.")
                    manual.isChecked && (manualSl <= 0.0 || manualTp <= manualSl) -> showMessage("TP/SL TIDAK VALID", "TP harus lebih besar daripada SL.")
                    else -> {
                        prefs.edit().putString(KEY_MODE, mode.selectedItem.toString()).putBoolean(KEY_MANUAL, manual.isChecked).putString(KEY_MANUAL_SL, manualSl.toString()).putString(KEY_MANUAL_TP, manualTp.toString()).apply()
                        startButton.isEnabled = false
                        runtimeCard.text = "MENYIAPKAN PORTFOLIO…"
                        val payload = allocations.entries.joinToString(";") { "${it.key}=${it.value}" }
                        send(MireiForegroundService.ACTION_START, Intent(this, MireiForegroundService::class.java).setAction(MireiForegroundService.ACTION_START).apply {
                            putExtra(MireiForegroundService.EXTRA_SYMBOL, allocations.keys.first())
                            putExtra(MireiForegroundService.EXTRA_EXCHANGE, selectedExchange)
                            putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, payload)
                        })
                        dialog.dismiss()
                    }
                }
            }
        }
        dialog.show()
    }

    private fun showRiskDialog() {
        val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY")
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 4, 18, 4) }
        val mode = spinner(modes); val savedMode = prefs.getString(KEY_MODE, "BALANCED") ?: "BALANCED"; mode.setSelection(modes.indexOf(savedMode).coerceAtLeast(0))
        root.addView(text("Risk profile", 12f, true)); root.addView(mode)
        val manual = CheckBox(this).apply { text = "TP/SL manual · kunci profile" }; root.addView(manual)
        val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.10") ?: "0.10"); val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "0.35") ?: "0.35")
        root.addView(text("Stop Loss %", 11f)); root.addView(sl); root.addView(text("Take Profit %", 11f)); root.addView(tp)
        manual.isChecked = prefs.getBoolean(KEY_MANUAL, false); mode.isEnabled = !manual.isChecked; sl.isEnabled = manual.isChecked; tp.isEnabled = manual.isChecked
        manual.setOnCheckedChangeListener { _, checked -> mode.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        AlertDialog.Builder(this).setTitle("PENGATURAN RISIKO / EXIT").setView(root).setNegativeButton("BATAL", null).setPositiveButton("SIMPAN") { _, _ ->
            val slValue = sl.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; val tpValue = tp.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
            if (manual.isChecked && (slValue <= 0.0 || tpValue <= slValue)) { showMessage("TP/SL TIDAK VALID", "TP harus lebih besar daripada SL."); return@setPositiveButton }
            prefs.edit().putString(KEY_MODE, mode.selectedItem.toString()).putBoolean(KEY_MANUAL, manual.isChecked).putString(KEY_MANUAL_SL, slValue.toString()).putString(KEY_MANUAL_TP, tpValue.toString()).apply()
            send(MireiForegroundService.ACTION_APPLY_RISK)
        }.show()
    }

    private fun updateControls() {
        val active = currentState == "RUNNING" || currentState == "HOLD"
        startButton.isVisibleSafe = !active
        riskButton.isVisibleSafe = active
        holdButton.isVisibleSafe = currentState == "RUNNING"
        closeAllButton.isVisibleSafe = active
        stopButton.isVisibleSafe = currentState == "RUNNING" || currentState == "HOLD"
        refreshButton.isVisibleSafe = true
        deleteButton.isVisibleSafe = true
        startButton.isEnabled = true
    }

    private fun requestRefresh() = send(MireiForegroundService.ACTION_REFRESH)

    private fun send(action: String, intent: Intent = Intent(this, MireiForegroundService::class.java).setAction(action)) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent)
    }

    private fun confirmDeleteHistory() {
        AlertDialog.Builder(this).setTitle("HAPUS HISTORY?").setMessage("History keputusan, audit, dan trade yang sudah CLOSED akan dihapus. Posisi OPEN tidak dihapus agar risiko aktif tetap aman.").setNegativeButton("BATAL", null).setPositiveButton("HAPUS") { _, _ -> send(MireiForegroundService.ACTION_DELETE_HISTORY); renderHistory() }.show()
    }

    private fun parseScanner(line: String): ScannerRow? {
        val p = line.split('|'); if (p.size < 6) return null
        return runCatching { ScannerRow(p[0], p[1].toDouble(), p[2].toDouble(), p[3].toDouble(), p[4].toDouble(), p[5].toDouble()) }.getOrNull()
    }

    private fun parsePosition(line: String): PositionRow? {
        val map = line.split('|').mapNotNull { token -> token.split('=', limit = 2).takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap()
        val coin = line.substringBefore('|').trim()
        return runCatching {
            PositionRow(coin, map.getValue("stake").toDouble(), map.getValue("entry").toDouble(), map.getValue("current").toDouble(), map.getValue("value").toDouble(), map.getValue("unrealized").toDouble(), map.getValue("tp").toDouble(), map.getValue("sl").toDouble(), map.getValue("tp_pct").toDouble(), map.getValue("sl_pct").toDouble())
        }.getOrNull()
    }

    private fun tableRow(values: List<String>, header: Boolean): TableRow = TableRow(this).apply {
        values.forEach { value ->
            addView(text(value, if (header) 11f else 10.5f, header).apply {
                setPadding(8, 8, 8, 8); minWidth = if (header) 78 else 72
                if (header) background = panel()
            })
        }
    }

    private fun horizontal(view: View): HorizontalScrollView = HorizontalScrollView(this).apply { addView(view, ViewGroup.LayoutParams(-2, -2)) }
    private fun cardText(value: String): TextView = text(value, 14f, false).apply { setPadding(14, 14, 14, 14); background = panel() }
    private fun metricCard(label: String, value: Int): TextView = text("$label\n$value", 21f, true).apply { gravity = Gravity.CENTER; setPadding(6, 14, 6, 14); background = panel() }
    private fun cardView(label: String, child: View, height: Int? = null): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(14, 12, 14, 12); background = panel(); addView(text(label, 11f, true)); addView(child, margin(0, 8, 0, 0)); if (height != null) child.layoutParams = LinearLayout.LayoutParams(-1, height) }
    private fun addSection(label: String) { root.addView(text(label, 13f, true).apply { setPadding(2, 16, 2, 6) }) }
    private fun actionButton(label: String, action: () -> Unit): Button = Button(this).apply { text = label; isAllCaps = false; minHeight = 56; textSize = 14f; setOnClickListener { action() } }
    private fun spinner(values: List<String>): Spinner = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, values) }
    private fun moneyEdit(value: String): EditText = EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(value) }
    private fun percentEdit(value: String): EditText = moneyEdit(value)
    private fun margin(l: Int, t: Int, r: Int, b: Int) = LinearLayout.LayoutParams(-1, -2).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }
    private fun panel() = GradientDrawable().apply { cornerRadius = 18f; setColor(0xff18222b.toInt()); setStroke(1, 0xff33424d.toInt()) }
    private fun text(value: String, size: Float, bold: Boolean): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(0xffeeeeee.toInt()); if (bold) typeface = Typeface.DEFAULT_BOLD; setLineSpacing(0f, 1.06f) }
    private fun fmt(value: Double) = "%.3f".format(Locale.US, value)
    private fun signed(value: Double) = if (value > 0.0) "+${fmt(value)}" else fmt(value)
    private fun signedMoney(value: Double) = if (value > 0.0) "+${numberFormat.format(value)}" else numberFormat.format(value)
    private fun formatEpoch(ms: Long) = if (ms <= 0L) "n/a" else SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(Date(ms))
    private fun humanReason(reason: String): String = when (reason) {
        "agent_conflict_requires_human_decision" -> "Agent saling berlawanan; mode Suggestion meminta konfirmasi manusia."
        "agent_consensus_or_take_over" -> "Belum ada keselarasan agent yang cukup untuk entry otomatis."
        "forecast_confidence_low" -> "Keyakinan forecast berada di bawah batas entry."
        "momentum_not_positive" -> "Momentum jangka pendek belum cukup positif."
        "position_limit" -> "Batas maksimum posisi sudah tercapai."
        else -> reason.replace('_', ' ')
    }
    private fun requestNotificationPermissionIfNeeded() { if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS) }
    private fun showMessage(title: String, message: String) { AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("OK", null).show() }

    private var Button.isVisibleSafe: Boolean
        get() = visibility == View.VISIBLE
        set(value) { visibility = if (value) View.VISIBLE else View.GONE }

    class SparklineView(context: Context) : View(context) {
        private val values = mutableListOf<Double>(); private val paint = Paint(Paint.ANTI_ALIAS_FLAG); private val path = Path()
        fun setValues(input: List<Double>) { values.clear(); values.addAll(input); invalidate() }
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas); if (values.size < 2) return
            val min = values.minOrNull() ?: 0.0; val max = values.maxOrNull() ?: min; val span = kotlin.math.max(1e-9, max - min)
            path.reset(); values.forEachIndexed { i, v -> val x = i * width.toFloat() / (values.size - 1); val y = height - ((v - min) / span * height); if (i == 0) path.moveTo(x, y.toFloat()) else path.lineTo(x, y.toFloat()) }
            paint.style = Paint.Style.STROKE; paint.strokeWidth = 4f; paint.color = 0xff22ccaa.toInt(); canvas.drawPath(path, paint)
        }
    }

    data class ScannerRow(val coin: String, val price: Double, val change1m: Double, val momentum: Double, val trend: Double, val volumeShare: Double)
    data class PositionRow(val coin: String, val stake: Double, val entry: Double, val current: Double, val value: Double, val unrealized: Double, val tp: Double, val sl: Double, val tpPct: Double, val slPct: Double)

    companion object {
        private const val PREFS_NAME = "mirei_settings"
        private const val KEY_MODE = "mode"
        private const val KEY_MANUAL = "manual_risk"
        private const val KEY_MANUAL_SL = "manual_sl"
        private const val KEY_MANUAL_TP = "manual_tp"
        private const val REQUEST_NOTIFICATIONS = 2001
    }
}
