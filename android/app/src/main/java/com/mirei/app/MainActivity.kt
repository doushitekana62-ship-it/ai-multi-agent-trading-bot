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
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.SecureCredentialStore
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var statusCard: TextView
    private lateinit var content: LinearLayout
    private lateinit var chart: SparklineView
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, MODE_PRIVATE) }
    private val credentials by lazy { SecureCredentialStore(this) }
    private val priceSeries = mutableListOf<Double>()
    private var currentState = "STOP"
    private var currentIntent: Intent? = null
    private var currentMenu = Menu.RINGKASAN

    private enum class Menu(val label: String) {
        RINGKASAN("RINGKASAN"), PASAR("PASAR"), POSISI("POSISI"), AKTIVITAS("AKTIVITAS"), KEPUTUSAN("KEPUTUSAN"), RISIKO("RISIKO"), EXCHANGE("EXCHANGE / API"), PENGATURAN("PENGATURAN"), AUDIT("LOG / AUDIT")
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != MireiForegroundService.ACTION_STATUS) return
            currentIntent = intent
            currentState = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP"
            val price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0)
            if (price > 0.0) { priceSeries += price; while (priceSeries.size > 120) priceSeries.removeAt(0); chart.setValues(priceSeries) }
            renderHeader()
            renderCurrentMenu()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        buildShell()
        requestRefresh()
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(MireiForegroundService.ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED) else registerReceiver(receiver, filter)
        requestRefresh()
    }

    override fun onStop() {
        runCatching { unregisterReceiver(receiver) }
        super.onStop()
    }

    private fun buildShell() {
        val shell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 16, 12, 18) }
        shell.addView(text("Mirei", 30f, true))
        shell.addView(text("Asisten trading crypto · lokal · paper trading", 13f), margin(0, 2, 0, 10))
        statusCard = cardText("BERHENTI · PAPER ONLY")
        shell.addView(statusCard, margin(0, 0, 0, 8))

        val menuScroll = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false }
        val menuBar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        Menu.values().forEach { menu ->
            menuBar.addView(Button(this).apply { text = menu.label; textSize = 12f; setOnClickListener { currentMenu = menu; renderCurrentMenu() } }, LinearLayout.LayoutParams(-2, -2).apply { rightMargin = 5 })
        }
        menuScroll.addView(menuBar, ViewGroup.LayoutParams(-2, -2))
        shell.addView(menuScroll, margin(0, 0, 0, 8))

        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content, ViewGroup.LayoutParams(-1, -2)) }
        shell.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(shell)
        renderCurrentMenu()
    }

    private fun renderHeader() {
        val intent = currentIntent ?: return
        val state = when (currentState) { "RUNNING" -> "BERJALAN"; "HOLD" -> "HOLD"; else -> "BERHENTI" }
        val exchange = intent.getStringExtra(MireiForegroundService.EXTRA_EXCHANGE)?.uppercase(Locale.US) ?: "INDODAX"
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val cash = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        statusCard.text = "$state · PAPER ONLY · $exchange\nNilai Rp ${numberFormat.format(equity)} · Kas Rp ${numberFormat.format(cash)} · Posisi $positions"
    }

    private fun renderCurrentMenu() {
        content.removeAllViews()
        when (currentMenu) {
            Menu.RINGKASAN -> renderSummary()
            Menu.PASAR -> renderMarket()
            Menu.POSISI -> renderPositions()
            Menu.AKTIVITAS -> renderActivity()
            Menu.KEPUTUSAN -> renderDecision()
            Menu.RISIKO -> renderRisk()
            Menu.EXCHANGE -> renderExchange()
            Menu.PENGATURAN -> renderSettings()
            Menu.AUDIT -> renderAudit()
        }
    }

    private fun renderSummary() {
        addTitle("RINGKASAN")
        val intent = currentIntent
        if (intent == null) content.addView(cardText("Belum ada data runtime. Tekan SEGARKAN DATA."))
        else {
            val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
            val cash = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
            val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0)
            val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
            val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
            val internet = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
            val healthy = intent.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)
            val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
            val confidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0)
            val reason = humanReason(intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty())
            content.addView(cardText("STATUS\n${if (currentState == "RUNNING") "BERJALAN" else if (currentState == "HOLD") "HOLD" else "BERHENTI"}\n\nMODE\nPAPER ONLY\n\nNILAI AKUN\nRp ${numberFormat.format(equity)}\n\nKAS TERSEDIA\nRp ${numberFormat.format(cash)}\n\nPnL TEREALISASI HARI INI\nRp ${signedMoney(pnl)}\n\nPOSISI TERBUKA\n$positions\n\nKESEHATAN\nInternet: ${if (internet) "OK" else "PUTUS"}\nMarket: ${if (fresh) "SEGAR" else "STALE"}\nExchange: ${if (healthy) "OK" else "TIDAK SIAP"}\n\nKEPUTUSAN TERAKHIR\n$action · ${(confidence * 100).toInt()}%\n$reason", 15f))
        }
        addTitle("TINDAKAN")
        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        r1.addView(actionButton("MULAI") { showStartDialog() }, weight())
        r1.addView(actionButton("SEGARKAN DATA") { requestRefresh() }, weight())
        content.addView(r1)
        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        r2.addView(actionButton("HOLD") { send(MireiForegroundService.ACTION_HOLD) }, weight())
        r2.addView(actionButton("BERHENTI") { send(MireiForegroundService.ACTION_STOP) }, weight())
        content.addView(r2)
        content.addView(actionButton("TUTUP SEMUA POSISI") { send(MireiForegroundService.ACTION_CLOSE_ALL) })
        content.addView(actionButton("HAPUS RIWAYAT") { confirmDeleteHistory() })

        val latest = MireiDatabase(this).recentTrades(1).firstOrNull()
        if (latest != null && latest.status == "CLOSED") content.addView(cardText("SIKLUS TERAKHIR\n${latest.symbol}: DITUTUP · ${humanExitReason(latest.exitReason)}\nPnL: Rp ${signedMoney(latest.pnlIdr)}\n\nMirei tidak menunggu nominal rugi sebelumnya kembali. Re-entry hanya dilakukan bila strategy, freshness, risk, dan mode Suggestion mengizinkan entry baru. Lihat AKTIVITAS dan KEPUTUSAN untuk bukti."))
    }

    private fun renderMarket() {
        addTitle("PASAR")
        val intent = currentIntent ?: run { content.addView(cardText("Menunggu snapshot pasar.")); return }
        content.addView(cardText("${intent.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: MireiForegroundService.DEFAULT_SYMBOL}\nHarga Rp ${numberFormat.format(intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0))}\n1 menit ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0))}% · 5 menit ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0))}% · 15 menit ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0))}%\nMomentum ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0))}% · Trend ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0))}%\nFlow ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0))}% · Forecast ${(intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0) * 100).toInt()}%\nSpread ${fmt(intent.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0))}%\nData ${if (intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}", 14f))
        addTitle("GRAFIK HARGA")
        chart = SparklineView(this); chart.setValues(priceSeries); content.addView(cardView("HARGA LIVE", chart, 220))
        addTitle("SCANNER")
        val rows = intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty().lines().filter { it.isNotBlank() }.take(10)
        if (rows.isEmpty()) content.addView(cardText("Belum ada hasil scanner.")) else rows.forEach { line ->
            val p = line.split('|')
            if (p.size >= 6) content.addView(cardText("${p[0]}\nHarga Rp ${p[1]} · 1M ${p[2]}% · Momentum ${p[3]}% · Trend ${p[4]}% · Volume ${p[5]}%", 13f))
        }
    }

    private fun renderPositions() {
        addTitle("POSISI AKTIF")
        val rows = parsePositions(currentIntent?.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        if (rows.isEmpty()) { content.addView(cardText("Tidak ada posisi terbuka.")); return }
        rows.forEach { row -> content.addView(cardView(row["symbol"].orEmpty(), text("Modal Rp ${numberFormat.format(row["stake"].toDouble())}\nEntry Rp ${numberFormat.format(row["entry"].toDouble())}\nSekarang Rp ${numberFormat.format(row["current"].toDouble())}\nNilai Rp ${numberFormat.format(row["value"].toDouble())}\nPnL belum terealisasi Rp ${signedMoney(row["unrealized"].toDouble())}\n\nTP Rp ${numberFormat.format(row["tp"].toDouble())} (+${row["tp_pct"]}%)\nSL Rp ${numberFormat.format(row["sl"].toDouble())} (-${row["sl_pct"]}%)\nAsal: ${humanEntryReason(row["entry_reason"].orEmpty())}", 14f))) }
    }

    private fun renderActivity() {
        addTitle("AKTIVITAS")
        content.addView(cardText("Urutan lifecycle terlihat di sini: OPEN/HOLDING AWAL → CLOSE → modal kembali ke kas → RE-ENTRY jika gate entry kembali valid. Tidak ada aturan recovery nominal rugi."))
        val db = MireiDatabase(this)
        db.recentTrades(50).forEach { trade ->
            val entry = humanEntryReason(trade.entryReason)
            val status = if (trade.status == "OPEN") "TERBUKA" else "DITUTUP"
            val exit = trade.exitReason?.let(::humanExitReason) ?: "—"
            content.addView(cardText("${formatEpoch(trade.closedAtEpochMs ?: trade.openedAtEpochMs)} · ${trade.symbol}\nMasuk: $entry\nStatus: $status\nModal: Rp ${numberFormat.format(trade.stakeIdr)}\nEntry: Rp ${numberFormat.format(trade.entryPrice ?: 0.0)}\nKeluar: ${trade.exitPrice?.let { "Rp ${numberFormat.format(it)}" } ?: "—"}\nPnL: Rp ${signedMoney(trade.pnlIdr)}\nAlasan keluar: $exit"))
        }
    }

    private fun renderDecision() {
        addTitle("KEPUTUSAN")
        val intent = currentIntent ?: run { content.addView(cardText("Belum ada keputusan.")); return }
        val gates = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty()
        content.addView(cardText("AKSI\n${intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"} · ${(intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()}%\n\nMENGAPA\n${humanReason(intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty())}\n\nGATE MASUK\n${if (gates.isBlank()) "Semua gate entry lolos." else humanReasons(gates)}\n\nBUKTI MARKET\nMomentum ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0))}%\nTrend ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0))}%\nFlow ${signed(intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0))}%\nForecast ${(intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0) * 100).toInt()}%\n\nEKSEKUSI TERBARU\n${intent.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Tidak ada OPEN/CLOSE pada tick ini." }}", 14f))
        addTitle("AGENT")
        intent.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty().split("\n\n").filter { it.isNotBlank() }.forEach { block -> content.addView(cardText(block.replace("=>", "\n").replace(" | ", "\n").replace('_', ' '), 13f)) }
    }

    private fun renderRisk() {
        addTitle("RISIKO")
        val mode = prefs.getString(KEY_MODE, "BALANCED") ?: "BALANCED"
        val manual = prefs.getBoolean(KEY_MANUAL, false)
        val sl = prefs.getString(KEY_MANUAL_SL, "0.10") ?: "0.10"
        val tp = prefs.getString(KEY_MANUAL_TP, "0.35") ?: "0.35"
        content.addView(cardText("PROFIL\n$mode\n\nTARGET\n${if (manual) "Manual: SL $sl% · TP $tp%" else "Otomatis sesuai profil"}\n\nBATAS\nModal Rp 150.000\nUkuran dasar Rp 50.000\nMaksimum 3 posisi\nDaily loss 3%\nLoss beruntun maksimum 3\n\nSAFETY\nMarket stale → HOLD\nInternet putus → HOLD + notifikasi\nExchange error → STOP + notifikasi\nSuggestion conflict → perlu keputusan manusia", 14f))
        content.addView(actionButton("UBAH PROFIL RISIKO") { showRiskDialog() })
    }

    private fun renderExchange() {
        addTitle("EXCHANGE / API")
        content.addView(cardText("Layar ini menyiapkan koneksi exchange untuk tahap live. Saat ini runtime Android tetap PAPER ONLY dan hanya memakai data publik Indodax. Menyimpan API key tidak mengaktifkan live order. Gunakan kredensial TRADE ONLY dan tanpa WITHDRAWAL."))
        MireiForegroundService.SUPPORTED_EXCHANGES.forEach { exchange ->
            val label = exchange.uppercase(Locale.US)
            content.addView(cardText("$label\nKredensial: ${if (credentials.has(exchange)) "TERSIMPAN AMAN" else "BELUM ADA"}\nLive order: BELUM AKTIF"))
            content.addView(actionButton(if (credentials.has(exchange)) "UBAH $label API" else "KONFIGURASI $label API") { showExchangeDialog(exchange) })
        }
    }

    private fun renderSettings() {
        addTitle("PENGATURAN")
        content.addView(cardText("Bahasa\nIndonesia\n\nDecision Mode\nSuggestion\n\nRisk Profile\n${prefs.getString(KEY_MODE, "BALANCED")}\n\nRuntime\nForeground service berjalan terpisah dari tampilan Activity. SEGARKAN DATA hanya menyegarkan tampilan/data; bukan heartbeat trading.", 14f))
        content.addView(actionButton("MULAI / ATUR PORTFOLIO") { showStartDialog() })
        content.addView(actionButton("PENGATURAN RISIKO") { showRiskDialog() })
    }

    private fun renderAudit() {
        addTitle("LOG / AUDIT")
        val logs = MireiDatabase(this).recentAudit(100)
        if (logs.isEmpty()) content.addView(cardText("Belum ada log audit."))
        logs.forEach { row -> content.addView(cardText("${formatEpoch(row.createdAtEpochMs)} · ${humanEventType(row.eventType)}\n${row.details.replace('_', ' ')}", 12.5f)) }
    }

    private fun showStartDialog() {
        val dialogRoot = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 4, 18, 4) }
        dialogRoot.addView(text("COIN AWAL · MAKS 3", 12f, true))
        val coins = mutableListOf<Spinner>(); val amounts = mutableListOf<EditText>()
        repeat(3) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val coin = spinner(MireiForegroundService.SUPPORTED_MARKETS); val amount = moneyEdit("0")
            coins += coin; amounts += amount
            row.addView(coin, LinearLayout.LayoutParams(0, -2, 1.1f)); row.addView(amount, LinearLayout.LayoutParams(0, -2, 0.9f).apply { leftMargin = 8 }); dialogRoot.addView(row)
        }
        dialogRoot.addView(text("Total alokasi maksimal Rp 150.000. Ini adalah holding awal, bukan BUY.", 11f), margin(0, 8, 0, 5))
        dialogRoot.addView(text("EXCHANGE", 12f, true)); val exchange = spinner(MireiForegroundService.SUPPORTED_EXCHANGES.map { if (it == MireiForegroundService.DEFAULT_EXCHANGE) "$it · DATA PUBLIK" else "$it · FUTURE API" }); dialogRoot.addView(exchange)
        dialogRoot.addView(text("PROFIL RISIKO", 12f, true), margin(0, 10, 0, 2)); val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY"); val mode = spinner(modes); dialogRoot.addView(mode)
        val manual = CheckBox(this).apply { text = "TP/SL manual" }; dialogRoot.addView(manual)
        val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.10") ?: "0.10"); val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "0.35") ?: "0.35")
        dialogRoot.addView(text("Stop Loss %", 11f)); dialogRoot.addView(sl); dialogRoot.addView(text("Take Profit %", 11f)); dialogRoot.addView(tp); sl.isEnabled = false; tp.isEnabled = false
        manual.setOnCheckedChangeListener { _, checked -> sl.isEnabled = checked; tp.isEnabled = checked; mode.isEnabled = !checked }
        val dialog = AlertDialog.Builder(this).setTitle("MULAI PORTFOLIO PAPER").setView(dialogRoot).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val allocations = linkedMapOf<String, Double>()
                coins.indices.forEach { i -> val amount = amounts[i].text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; if (amount > 0.0) allocations[coins[i].selectedItem.toString()] = amount }
                val total = allocations.values.sum(); val selectedExchange = MireiForegroundService.SUPPORTED_EXCHANGES[exchange.selectedItemPosition]
                val manualSl = sl.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; val manualTp = tp.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
                when {
                    allocations.isEmpty() || total > 150000.0001 -> showMessage("ALOKASI TIDAK VALID", "Masukkan 1–3 coin dengan total maksimal Rp 150.000.")
                    selectedExchange != MireiForegroundService.DEFAULT_EXCHANGE -> showMessage("EXCHANGE BELUM AKTIF", "Paper runtime Android saat ini hanya menggunakan data publik Indodax.")
                    manual.isChecked && (manualSl <= 0.0 || manualTp <= manualSl) -> showMessage("TP/SL TIDAK VALID", "TP harus lebih besar daripada SL.")
                    else -> {
                        prefs.edit().putString(KEY_MODE, mode.selectedItem.toString()).putBoolean(KEY_MANUAL, manual.isChecked).putString(KEY_MANUAL_SL, manualSl.toString()).putString(KEY_MANUAL_TP, manualTp.toString()).apply()
                        val payload = allocations.entries.joinToString(";") { "${it.key}=${it.value}" }
                        send(MireiForegroundService.ACTION_START, Intent(this, MireiForegroundService::class.java).setAction(MireiForegroundService.ACTION_START).apply { putExtra(MireiForegroundService.EXTRA_SYMBOL, allocations.keys.first()); putExtra(MireiForegroundService.EXTRA_EXCHANGE, selectedExchange); putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, payload) })
                        dialog.dismiss()
                    }
                }
            }
        }
        dialog.show()
    }

    private fun showRiskDialog() {
        val modes = listOf("BALANCED", "AGGRESSIVE", "SAFETY")
        val dialogRoot = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 4, 18, 4) }
        val mode = spinner(modes); val savedMode = prefs.getString(KEY_MODE, "BALANCED") ?: "BALANCED"; mode.setSelection(modes.indexOf(savedMode).coerceAtLeast(0)); dialogRoot.addView(text("Profil risiko", 12f, true)); dialogRoot.addView(mode)
        val manual = CheckBox(this).apply { text = "TP/SL manual" }; dialogRoot.addView(manual)
        val sl = percentEdit(prefs.getString(KEY_MANUAL_SL, "0.10") ?: "0.10"); val tp = percentEdit(prefs.getString(KEY_MANUAL_TP, "0.35") ?: "0.35"); dialogRoot.addView(text("Stop Loss %", 11f)); dialogRoot.addView(sl); dialogRoot.addView(text("Take Profit %", 11f)); dialogRoot.addView(tp)
        manual.isChecked = prefs.getBoolean(KEY_MANUAL, false); mode.isEnabled = !manual.isChecked; sl.isEnabled = manual.isChecked; tp.isEnabled = manual.isChecked; manual.setOnCheckedChangeListener { _, checked -> mode.isEnabled = !checked; sl.isEnabled = checked; tp.isEnabled = checked }
        AlertDialog.Builder(this).setTitle("PENGATURAN RISIKO").setView(dialogRoot).setNegativeButton("BATAL", null).setPositiveButton("SIMPAN") { _, _ ->
            val s = sl.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0; val t = tp.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
            if (manual.isChecked && (s <= 0.0 || t <= s)) { showMessage("TP/SL TIDAK VALID", "TP harus lebih besar daripada SL."); return@setPositiveButton }
            prefs.edit().putString(KEY_MODE, mode.selectedItem.toString()).putBoolean(KEY_MANUAL, manual.isChecked).putString(KEY_MANUAL_SL, s.toString()).putString(KEY_MANUAL_TP, t.toString()).apply(); send(MireiForegroundService.ACTION_APPLY_RISK)
        }.show()
    }

    private fun showExchangeDialog(exchange: String) {
        val dialogRoot = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 4, 18, 4) }
        dialogRoot.addView(text("Exchange: ${exchange.uppercase(Locale.US)}", 15f, true))
        dialogRoot.addView(text("Gunakan API key TRADE ONLY. Jangan gunakan key dengan izin withdrawal.", 12f), margin(0, 6, 0, 8))
        val key = EditText(this).apply { hint = "API Key"; inputType = InputType.TYPE_CLASS_TEXT }
        val secret = EditText(this).apply { hint = "API Secret"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
        dialogRoot.addView(key); dialogRoot.addView(secret, margin(0, 6, 0, 0))
        dialogRoot.addView(text("Kredensial disimpan terenkripsi dengan Android Keystore. Penyimpanan ini tidak mengaktifkan live trading.", 11f), margin(0, 8, 0, 0))
        AlertDialog.Builder(this).setTitle("KONFIGURASI API").setView(dialogRoot).setNegativeButton("BATAL", null).setPositiveButton("SIMPAN") { _, _ ->
            val apiKey = key.text.toString().trim(); val apiSecret = secret.text.toString()
            if (apiKey.isBlank() || apiSecret.isBlank()) { showMessage("DATA TIDAK LENGKAP", "API Key dan API Secret wajib diisi."); return@setPositiveButton }
            credentials.put(exchange, apiKey, apiSecret); renderCurrentMenu()
        }.setNeutralButton("HAPUS KREDENSIAL") { _, _ -> credentials.delete(exchange); renderCurrentMenu() }.show()
    }

    private fun confirmDeleteHistory() = AlertDialog.Builder(this).setTitle("HAPUS RIWAYAT?").setMessage("Trade tertutup, keputusan, dan audit dihapus. Posisi terbuka tidak dihapus.").setNegativeButton("BATAL", null).setPositiveButton("HAPUS") { _, _ -> send(MireiForegroundService.ACTION_DELETE_HISTORY) }.show()
    private fun requestRefresh() = send(MireiForegroundService.ACTION_REFRESH)
    private fun send(action: String, intent: Intent = Intent(this, MireiForegroundService::class.java).setAction(action)) { if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(intent) else startService(intent) }
    private fun requestNotificationPermissionIfNeeded() { if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 42) }

    private fun addTitle(title: String) { content.addView(text(title, 18f, true), margin(0, 4, 0, 7)) }
    private fun actionButton(label: String, action: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { action() } }
    private fun text(value: String, size: Float = 14f, bold: Boolean = false): TextView = TextView(this).apply { text = value; textSize = size; setPadding(8, 7, 8, 7); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD) }
    private fun cardText(value: String, size: Float = 14f): TextView = text(value, size).apply { setPadding(12, 12, 12, 12); background = panel() }
    private fun cardView(title: String, child: View, height: Int? = null): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = panel(); setPadding(8, 8, 8, 8); addView(text(title, 12f, true)); addView(child, if (height == null) ViewGroup.LayoutParams(-1, -2) else ViewGroup.LayoutParams(-1, height)) }
    private fun panel() = android.graphics.drawable.GradientDrawable().apply { cornerRadius = 18f; setStroke(1, 0x55304050) }
    private fun margin(l: Int, t: Int, r: Int, b: Int) = LinearLayout.LayoutParams(-1, -2).apply { setMargins(l, t, r, b) }
    private fun weight() = LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = 4 }
    private fun spinner(items: List<String>): Spinner = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, items) }
    private fun moneyEdit(value: String) = EditText(this).apply { hint = "Modal IDR"; setText(value); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL }
    private fun percentEdit(value: String) = EditText(this).apply { setText(value); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL }
    private fun showMessage(title: String, message: String) = AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("TUTUP", null).show()

    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { line ->
        val parts = line.split('|')
        buildMap { put("symbol", parts[0]); parts.drop(1).forEach { token -> val i = token.indexOf('='); if (i > 0) put(token.substring(0, i), token.substring(i + 1)) } }
    }.filter { it.containsKey("stake") }
    private fun humanReason(value: String): String = when (value) { "agent_conflict_requires_human_decision" -> "Agent belum selaras; mode Suggestion menahan entry otomatis."; "no_decision" -> "Belum ada keputusan."; else -> value.replace('_', ' ') }
    private fun humanReasons(value: String): String = value.split(" | ").joinToString("\n") { "• ${it.replace('_', ' ')}" }
    private fun humanExitReason(value: String?): String = when (value) { "stop_loss" -> "STOP LOSS"; "take_profit" -> "TAKE PROFIT"; "manual_close_all" -> "MANUAL"; "ai_close" -> "AI CLOSE"; else -> value?.replace('_', ' ') ?: "—" }
    private fun humanEntryReason(value: String): String = when (value) { "initial_holding" -> "HOLDING AWAL"; "re_entry" -> "RE-ENTRY"; "limit_fill" -> "LIMIT FILL"; else -> "ENTRY" }
    private fun humanEventType(value: String): String = when (value) { "SL_CLOSE" -> "STOP LOSS"; "TP_CLOSE" -> "TAKE PROFIT"; "RE_ENTRY" -> "RE-ENTRY"; "OPEN" -> "OPEN"; "MANUAL_CLOSE" -> "TUTUP MANUAL"; else -> value.replace('_', ' ') }
    private fun signed(value: Double): String = if (value >= 0) "+${fmt(value)}" else fmt(value)
    private fun fmt(value: Double): String = "%.3f".format(Locale.US, value)
    private fun signedMoney(value: Double): String = if (value >= 0) "+${numberFormat.format(value)}" else numberFormat.format(value)
    private fun formatEpoch(epochMs: Long): String = SimpleDateFormat("dd/MM HH:mm:ss", Locale("id", "ID")).format(Date(epochMs))

    companion object { private const val PREFS_NAME = "mirei_settings"; private const val KEY_MODE = "mode"; private const val KEY_MANUAL = "manual_risk"; private const val KEY_MANUAL_SL = "manual_sl"; private const val KEY_MANUAL_TP = "manual_tp" }
}

private class SparklineView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 3f; style = Paint.Style.STROKE }
    private val path = Path()
    private var values: List<Double> = emptyList()
    fun setValues(next: List<Double>) { values = next.toList(); invalidate() }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (values.size < 2) return
        val min = values.minOrNull() ?: return; val max = values.maxOrNull() ?: return; val range = (max - min).takeIf { it > 0 } ?: 1.0
        path.reset()
        values.forEachIndexed { index, value ->
            val x = width * index.toFloat() / (values.size - 1).coerceAtLeast(1)
            val y = height - ((value - min) / range * (height - 12)).toFloat() - 6f
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        canvas.drawPath(path, paint)
    }
}
