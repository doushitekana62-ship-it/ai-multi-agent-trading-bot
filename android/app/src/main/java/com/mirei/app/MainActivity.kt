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
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.Switch
import android.widget.TextView
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.SecureCredentialStore
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var content: LinearLayout
    private lateinit var statusCard: TextView
    private val handler = Handler(Looper.getMainLooper())
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
    private val credentials by lazy { SecureCredentialStore(this) }
    private val uiPrefs by lazy { getSharedPreferences("mirei_ui", MODE_PRIVATE) }
    private val riskPrefs by lazy { getSharedPreferences("mirei_settings", MODE_PRIVATE) }
    private var currentIntent: Intent? = null
    private var currentMenu = Menu.RINGKASAN
    private var menuSpinner: Spinner? = null
    private var liveSwitchUpdating = false

    private enum class Menu(val label: String) {
        RINGKASAN("RINGKASAN"), PASAR("PASAR"), POSISI("POSISI"), AKTIVITAS("AKTIVITAS"),
        KEPUTUSAN("KEPUTUSAN"), RISIKO("RISIKO"), EXCHANGE("EXCHANGE / API"),
        PENGATURAN("PENGATURAN"), AUDIT("LOG / AUDIT")
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != MireiForegroundService.ACTION_STATUS) return
            currentIntent = intent
            renderHeader()
            renderCurrentMenu()
        }
    }

    private val clockRunnable = object : Runnable {
        override fun run() {
            renderHeader()
            if (currentMenu == Menu.RINGKASAN) renderCurrentMenu()
            handler.postDelayed(this, 1_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        buildShell()
        requestRefresh()
        handler.post(clockRunnable)
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

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun buildShell() {
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(12, 14, 12, 18)
            setBackgroundColor(Color.rgb(48, 48, 48))
        }
        shell.addView(text("Mirei", 30f, true))
        shell.addView(text("Asisten trading crypto · lokal · paper trading", 14f), margin(0, 2, 0, 8))
        statusCard = card("BERHENTI · PAPER ONLY")
        shell.addView(statusCard, margin(0, 0, 0, 8))

        shell.addView(text("MENU", 12f, true), margin(0, 0, 0, 2))
        val menu = Spinner(this)
        menuSpinner = menu
        menu.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, Menu.values().map { it.label })
        menu.setSelection(currentMenu.ordinal)
        menu.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val selected = Menu.values().getOrNull(position) ?: return
                if (selected != currentMenu) {
                    currentMenu = selected
                    renderCurrentMenu()
                }
            }
        }
        shell.addView(menu, margin(0, 0, 0, 8))

        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, 16) }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content, ViewGroup.LayoutParams(-1, -2)) }
        shell.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(shell)
        renderCurrentMenu()
    }

    private fun renderHeader() {
        val i = currentIntent
        if (i == null) {
            statusCard.text = "BERHENTI · PAPER ONLY\nBelum ada status runtime."
            return
        }
        val state = when (i.getStringExtra(MireiForegroundService.EXTRA_STATE)) {
            "RUNNING" -> "BERJALAN"
            "HOLD" -> "JEDA / HOLD"
            else -> "BERHENTI"
        }
        val mode = if (uiPrefs.getBoolean("live_requested", false)) "REAL TRADE TERKUNCI" else "PAPER ONLY"
        val equity = i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val cash = i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val positions = i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        statusCard.text = "$state · $mode · ${i.getStringExtra(MireiForegroundService.EXTRA_EXCHANGE)?.uppercase(Locale.US) ?: "INDODAX"}\n" +
            "Nilai Rp ${numberFormat.format(equity)} · Kas Rp ${numberFormat.format(cash)} · Posisi $positions\nWaktu sesi: ${sessionClock(i)}"
    }

    private fun renderCurrentMenu() {
        content.removeAllViews()
        menuSpinner?.setSelection(currentMenu.ordinal, false)
        runCatching {
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
        }.onFailure { content.addView(card("UI tidak dapat membaca data terakhir.\n${it.javaClass.simpleName}: ${it.message ?: "error"}")) }
    }

    private fun renderSummary() {
        addTitle("RINGKASAN")
        val i = currentIntent
        if (i == null) { content.addView(card("Belum ada data runtime.")); addControls(); return }
        val action = i.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val confidence = (i.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()
        val reason = humanReason(i.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty())
        val pnl = i.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0)
        val health = "Internet: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)) "OK" else "PUTUS"}\n" +
            "Market: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}\n" +
            "Exchange: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)) "OK" else "TIDAK SIAP"}"
        val riskBlock = humanReasons(i.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty())
        val latestExecution = i.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Belum ada OPEN/CLOSE pada tick terakhir." }
        content.addView(card("STATUS\n${stateLabel(i.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP")}\n\nNILAI AKUN\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n\nKAS TERSEDIA\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n\nPnL TEREALISASI\nRp ${signedMoney(pnl)}\n\nPOSISI AKTIF\n${i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}\n\nKEPUTUSAN TERAKHIR\n$action · $confidence%\n$reason\n\nKESEHATAN\n$health", 14f))
        addTitle("EVENT TERAKHIR")
        content.addView(card(latestExecution, 13f))
        addTitle("GATE / BLOK RISIKO TERAKHIR")
        content.addView(card(riskBlock, 13f))
        addTitle("HITUNGAN KEPUTUSAN")
        content.addView(card("BUY / MASUK: ${i.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)}\nHOLD / TAHAN: ${i.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)}\nSELL / KELUAR: ${i.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)}\n\nAngka ini adalah jumlah keputusan engine selama sesi aktif, bukan jumlah order.", 14f))
        addTitle("WAKTU APLIKASI")
        content.addView(clockCard(i))
        addControls()
    }

    private fun addControls() {
        addTitle("TINDAKAN")
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row.addView(button("MULAI") { showStartDialog() }, weight())
        row.addView(button("SEGARKAN DATA") { requestRefresh() }, weight())
        content.addView(row)
        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row2.addView(button("JEDA / HOLD") { send(MireiForegroundService.ACTION_HOLD) }, weight())
        row2.addView(button("BERHENTI") { send(MireiForegroundService.ACTION_STOP) }, weight())
        content.addView(row2)
        content.addView(button("TUTUP SEMUA POSISI") { send(MireiForegroundService.ACTION_CLOSE_ALL) })
    }

    private fun renderMarket() {
        addTitle("PASAR")
        val i = currentIntent ?: run { content.addView(card("Belum ada snapshot pasar.")); return }
        val change1m = i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0)
        val change5m = i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0)
        val change15m = i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0)
        content.addView(card("${i.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: "BTC/IDR"}\nHarga Rp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0))}\n1M ${signed(change1m)}% · 5M ${signed(change5m)}% · 15M ${signed(change15m)}%\nMomentum ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0))}% · Trend ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0))}%\nFlow ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0))}% · Forecast ${(i.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0) * 100).toInt()}%\nSpread ${fmt(i.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0))}%\nData ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}", 14f))
        addTitle("GRAFIK PERUBAHAN 1M → 5M → 15M")
        content.addView(MiniMarketChartView(this, floatArrayOf(change15m.toFloat(), change5m.toFloat(), change1m.toFloat())))
        addTitle("SCANNER")
        val rows = i.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty().lines().filter { it.isNotBlank() }.take(10)
        if (rows.isEmpty()) content.addView(card("Belum ada hasil scanner.")) else rows.forEach { line ->
            val p = line.split('|')
            if (p.size >= 6) content.addView(card("${p[0]}\nHarga Rp ${p[1]}\n1M ${p[2]}% · Momentum ${p[3]}% · Trend ${p[4]}% · Porsi volume ${p[5]}%", 13f))
        }
    }

    private fun renderPositions() {
        addTitle("POSISI AKTIF")
        val rows = parsePositions(currentIntent?.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        if (rows.isEmpty()) { content.addView(card("Tidak ada posisi aktif.")); return }
        rows.forEach { row ->
            val entry = row["entry"].orEmpty().toDoubleOrNull() ?: 0.0
            val opened = row["opened"].orEmpty().toLongOrNull() ?: 0L
            val age = if (opened > 0L) formatAge(opened) else "—"
            val trailing = row["trailing"].orEmpty().toDoubleOrNull()
            val trailingText = trailing?.let { "Rp ${numberFormat.format(it)}" } ?: "dikelola otomatis sekitar 1R"
            val basis = riskBasisLabel(row["risk_basis"].orEmpty())
            val basisCapital = row["risk_capital"].orEmpty().toDoubleOrNull() ?: (row["stake"].orEmpty().toDoubleOrNull() ?: 0.0)
            content.addView(card("${row["symbol"].orEmpty()}\nModal posisi Rp ${numberFormat.format(row["stake"].orEmpty().toDoubleOrNull() ?: 0.0)}\nEntry Rp ${numberFormat.format(entry)}\nSekarang Rp ${numberFormat.format(row["current"].orEmpty().toDoubleOrNull() ?: 0.0)}\nNilai Rp ${numberFormat.format(row["value"].orEmpty().toDoubleOrNull() ?: 0.0)}\nPnL belum terealisasi Rp ${signedMoney(row["unrealized"].orEmpty().toDoubleOrNull() ?: 0.0)}\n\nTake Profit Rp ${numberFormat.format(row["tp"].orEmpty().toDoubleOrNull() ?: 0.0)}\nStop Loss Rp ${numberFormat.format(row["sl"].orEmpty().toDoubleOrNull() ?: 0.0)}\nDasar TP/SL: $basis\nModal acuan pertama: Rp ${numberFormat.format(basisCapital)}\nTrailing ${trailingText}\nUmur posisi $age\nAsal: ${humanEntryReason(row["entry_reason"].orEmpty())}", 14f))
        }
    }

    private fun renderActivity() {
        addTitle("AKTIVITAS · SESI INI")
        val sessionStart = currentIntent?.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L) ?: 0L
        content.addView(card("Hanya event sejak sesi ini ditampilkan.\n\nUrutan yang dicari:\nOPEN / HOLDING AWAL → CLOSE → modal kembali → RE-ENTRY bila gate valid.\n\nEvent RE-ENTRY adalah bukti paling jelas bahwa modal hasil close dipakai kembali setelah gate valid.", 13f))
        runCatching {
            val db = MireiDatabase(this)
            val trades = db.recentTrades(100).filter { sessionStart == 0L || it.openedAtEpochMs >= sessionStart }
            if (trades.isEmpty()) content.addView(card("Belum ada transaksi pada sesi ini."))
            trades.forEach { trade ->
                val status = if (trade.status == "OPEN") "TERBUKA" else "DITUTUP"
                val exit = trade.exitReason?.let(::humanExitReason) ?: "—"
                content.addView(card("${formatEpoch(trade.closedAtEpochMs ?: trade.openedAtEpochMs)} · ${trade.symbol}\nMasuk: ${humanEntryReason(trade.entryReason)}\nStatus: $status\nModal Rp ${numberFormat.format(trade.stakeIdr)}\nEntry Rp ${numberFormat.format(trade.entryPrice ?: 0.0)}\nKeluar ${trade.exitPrice?.let { "Rp ${numberFormat.format(it)}" } ?: "—"}\nPnL Rp ${signedMoney(trade.pnlIdr)}\nAlasan keluar: $exit", 13f))
            }
            val events = db.recentAudit(150).filter { sessionStart == 0L || it.createdAtEpochMs >= sessionStart }.filter { it.eventType in setOf("OPEN", "RE_ENTRY", "SL_CLOSE", "TP_CLOSE", "MANUAL_CLOSE", "HUMAN_VERIFIED_ENTRY", "SESSION_STOPPED", "SESSION_PAUSED", "SESSION_CLOSED") }
            if (events.isNotEmpty()) {
                addTitle("EVENT EKSEKUSI")
                events.forEach { e -> content.addView(card("${formatEpoch(e.createdAtEpochMs)} · ${humanEventType(e.eventType)}\n${e.details.replace('|', '\n').replace('_', ' ')}", 12.5f)) }
            }
        }.onFailure { content.addView(card("Riwayat sesi tidak dapat dibaca.\n${it.message ?: "database error"}")) }
    }

    private fun renderDecision() {
        addTitle("KEPUTUSAN")
        val i = currentIntent ?: run { content.addView(card("Belum ada keputusan.")); return }
        val action = i.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val confidence = (i.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()
        content.addView(card("AKSI\n$action · $confidence%\n\nMENGAPA\n${humanReason(i.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty())}\n\nGATE MASUK\n${humanReasons(i.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty())}\n\nEKSEKUSI TERBARU\n${i.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Tidak ada OPEN/CLOSE pada tick ini." }}", 14f))
        content.addView(card("JUMLAH KEPUTUSAN\nBUY ${i.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)}\nHOLD ${i.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)}\nSELL ${i.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)}", 14f))
        if (i.getBooleanExtra(MireiForegroundService.EXTRA_HUMAN_REQUIRED, false)) {
            addTitle("VERIFIKASI MANUSIA")
            content.addView(card("Mirei menentukan indikator yang BOLEH dipakai. Indikator yang bertentangan tidak dapat dipilih. Konfirmasi tetap melewati gate risiko, freshness, posisi maksimum, dan mode Suggestion.", 13f))
            content.addView(button("BUKA FORM VERIFIKASI") { showHumanVerifier() })
        }
        addTitle("AGENT")
        i.getStringExtra(MireiForegroundService.EXTRA_AGENT_SUMMARY).orEmpty().split("\n\n").filter { it.isNotBlank() }.forEach { block -> content.addView(card(block.replace("=>", "\n").replace(" | ", "\n").replace('_', ' '), 13f)) }
    }

    private fun showHumanVerifier() {
        val i = currentIntent ?: return
        val allowed = i.getStringExtra(MireiForegroundService.EXTRA_HUMAN_ALLOWED).orEmpty().split(',').filter { it.isNotBlank() }
        val blocked = i.getStringExtra(MireiForegroundService.EXTRA_HUMAN_BLOCKED).orEmpty().split(',').filter { it.isNotBlank() }
        if (allowed.isEmpty()) { AlertDialog.Builder(this).setTitle("Verifikasi manusia").setMessage("Tidak ada indikator BUY yang diizinkan Mirei. Tidak ada entry yang dapat dikonfirmasi.").setPositiveButton("TUTUP", null).show(); return }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 8, 20, 8) }
        box.addView(text("INDIKATOR YANG DIIZINKAN MIREI", 15f, true))
        val checks = allowed.map { agent -> CheckBox(this).apply { text = humanAgent(agent); isChecked = true } }
        checks.forEach { box.addView(it) }
        box.addView(text("INDIKATOR DITOLAK / TIDAK BOLEH DIPAKAI", 15f, true))
        blocked.forEach { agent -> box.addView(CheckBox(this).apply { text = "${humanAgent(agent)} · DITOLAK"; isEnabled = false }) }
        AlertDialog.Builder(this).setTitle("Perintah Verifikasi Manusia").setMessage("Centang semua indikator yang diizinkan untuk mengonfirmasi entry.").setView(box).setNegativeButton("BATAL", null).setPositiveButton("KONFIRMASI ENTRY", null).create().also { dialog ->
            dialog.setOnShowListener {
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    if (checks.all { it.isChecked }) {
                        val symbol = i.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: MireiForegroundService.DEFAULT_SYMBOL
                        send(MireiForegroundService.ACTION_HUMAN_VERIFY) { putExtra(MireiForegroundService.EXTRA_HUMAN_SYMBOL, symbol); putExtra(MireiForegroundService.EXTRA_HUMAN_AGENTS, allowed.joinToString(",")) }
                        dialog.dismiss()
                    }
                }
            }
        }.show()
    }

    private fun renderRisk() {
        addTitle("RISIKO / KELUAR")
        val mode = riskPrefs.getString("mode", "BALANCED") ?: "BALANCED"
        val manual = riskPrefs.getBoolean("manual_risk", false)
        val sl = riskPrefs.getString("manual_sl", "0.50") ?: "0.50"
        val tp = riskPrefs.getString("manual_tp", "1.00") ?: "1.00"
        val basis = riskPrefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name) ?: RiskReferenceMode.ENTRY_PRICE.name
        content.addView(card("Mode trading: ${modeLabel(mode)}\nDasar TP/SL: ${riskBasisLabel(basis)}\n${if (basis == RiskReferenceMode.INITIAL_CAPITAL.name) "Modal pertama tiap coin menjadi acuan nominal TP/SL; default sesi Rp50.000 per coin." else "Persentase TP/SL dihitung langsung dari harga entry coin."}\nTP/SL: ${if (manual) "MANUAL · TP $tp% / SL $sl%" else "OTOMATIS sesuai mode"}\nTrailing: AKTIF sekitar 1R dan hanya boleh memperketat stop, tidak melonggarkan risiko.\nMaksimum posisi: 3\nBatas rugi harian: 3%\nLoss beruntun maksimum: 3\n\nLoss sebelumnya bukan syarat recovery. Re-entry tetap menunggu gate Mirei.", 14f))
        content.addView(button("UBAH MODE / TP / SL") { showRiskDialog() })
        content.addView(button("TERAPKAN PENGATURAN RISIKO") { send(MireiForegroundService.ACTION_APPLY_RISK) })
    }

    private fun renderExchange() {
        addTitle("EXCHANGE / API")
        content.addView(card("Paper trading saat ini memakai market data Indodax. Adapter private/live belum diaktifkan. Menu ini hanya persiapan integrasi.", 13f))
        val liveSwitch = Switch(this).apply {
            text = "MODE REAL TRADE"
            textSize = 16f
            isChecked = uiPrefs.getBoolean("live_requested", false)
            setOnCheckedChangeListener { _, checked ->
                if (liveSwitchUpdating) return@setOnCheckedChangeListener
                if (checked) {
                    liveSwitchUpdating = true
                    isChecked = false
                    liveSwitchUpdating = false
                    uiPrefs.edit().putBoolean("live_requested", false).apply()
                    AlertDialog.Builder(this@MainActivity).setTitle("REAL TRADE TERKUNCI").setMessage("Live order belum tersedia pada Mirei build ini. Paper mode tetap aktif. Tidak ada order real yang dikirim.").setPositiveButton("OK", null).show()
                }
            }
        }
        content.addView(liveSwitch)
        content.addView(card("Penyimpanan API key: Android Keystore\nIzin yang dirancang: trade-only\nWithdrawal: DILARANG\nLive order adapter: BELUM TERSEDIA", 13f))
        val spinner = Spinner(this)
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, MireiForegroundService.SUPPORTED_EXCHANGES.map { it.uppercase(Locale.US) })
        content.addView(spinner)
        val key = EditText(this).apply { hint = "API key"; setSingleLine(true) }
        val secret = EditText(this).apply { hint = "API secret"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD; setSingleLine(true) }
        content.addView(key); content.addView(secret)
        content.addView(button("SIMPAN KREDENSIAL TERENKRIPSI") {
            val exchange = spinner.selectedItem.toString().lowercase(Locale.US)
            if (key.text.isNullOrBlank() || secret.text.isNullOrBlank()) return@button
            credentials.put(exchange, key.text.toString(), secret.text.toString())
            key.text.clear(); secret.text.clear()
            AlertDialog.Builder(this).setTitle("TERSIMPAN").setMessage("Kredensial disimpan melalui Android Keystore. Ini belum mengaktifkan live trading.").setPositiveButton("OK", null).show()
            renderCurrentMenu()
        })
        content.addView(card("Status kredensial\n${MireiForegroundService.SUPPORTED_EXCHANGES.joinToString("\n") { "${it.uppercase(Locale.US)}: ${if (credentials.has(it)) "TERSIMPAN" else "BELUM ADA"}" }}", 12.5f))
    }

    private fun renderSettings() {
        addTitle("PENGATURAN")
        val mode = riskPrefs.getString("mode", "BALANCED") ?: "BALANCED"
        val manual = riskPrefs.getBoolean("manual_risk", false)
        val sl = riskPrefs.getString("manual_sl", "0.50") ?: "0.50"
        val tp = riskPrefs.getString("manual_tp", "1.00") ?: "1.00"
        val basis = riskPrefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name) ?: RiskReferenceMode.ENTRY_PRICE.name
        val symbol = currentIntent?.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: "—"
        content.addView(card("Bahasa: Indonesia\nTimeframe utama: 1 menit\nDecision Mode: Suggestion\nCoin sesi: $symbol\nModal sesi: dipilih saat MULAI\nPosisi: maksimum 3\nMode trading: ${modeLabel(mode)}\nDasar TP/SL: ${riskBasisLabel(basis)}\nTP/SL: ${if (manual) "MANUAL · TP $tp% / SL $sl%" else "OTOMATIS"}", 14f))
        content.addView(button("PILIH MODE / TP / SL") { showRiskDialog() })
        content.addView(button("RESET TIMESTAMP") { send(MireiForegroundService.ACTION_RESET_CLOCK) })
        content.addView(button("SESI PAPER BARU") {
            AlertDialog.Builder(this).setTitle("Sesi paper baru").setMessage("Portfolio sesi aktif akan dibuang dari runtime dan dibuat ulang saat MULAI. Riwayat database tidak dihapus.").setNegativeButton("BATAL", null).setPositiveButton("RESET SESI") { _, _ -> send(MireiForegroundService.ACTION_RESET_SESSION) }.show()
        })
        content.addView(button("HAPUS RIWAYAT DATABASE") {
            AlertDialog.Builder(this).setTitle("Hapus riwayat").setMessage("Hanya riwayat database yang dihapus. Jangan gunakan ini sebagai reset portfolio.").setNegativeButton("BATAL", null).setPositiveButton("HAPUS") { _, _ -> send(MireiForegroundService.ACTION_DELETE_HISTORY) }.show()
        })
    }

    private fun renderAudit() {
        addTitle("LOG / AUDIT · SESI INI")
        val start = currentIntent?.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L) ?: 0L
        runCatching {
            val rows = MireiDatabase(this).recentAudit(200).filter { start == 0L || it.createdAtEpochMs >= start }
            if (rows.isEmpty()) content.addView(card("Belum ada log sesi."))
            rows.forEach { row -> content.addView(card("${formatEpoch(row.createdAtEpochMs)} · ${humanEventType(row.eventType)}\n${row.details.replace('|', '\n').replace('_', ' ')}", 12f)) }
        }.onFailure { content.addView(card("Log tidak dapat dibaca: ${it.message ?: "error"}")) }
    }

    private fun showStartDialog() {
        val outer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(6, 0, 6, 0) }
        outer.addView(text("1. COIN & MODAL", 14f, true))
        outer.addView(text("Pilih 1–3 coin. Modal pada baris coin menjadi modal beli pertama dan dapat menjadi acuan TP/SL.", 12.5f))
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val rows = MireiForegroundService.SUPPORTED_MARKETS.mapIndexed { index, market ->
            val check = CheckBox(this).apply { text = market; isChecked = index < 3 }
            val amount = EditText(this).apply {
                hint = "modal IDR"
                setSingleLine(true)
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                setText(if (index < 3) "50000" else "")
                isEnabled = check.isChecked
            }
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(amount, LinearLayout.LayoutParams(150, ViewGroup.LayoutParams.WRAP_CONTENT))
            list.addView(row)
            market to Pair(check, amount)
        }
        val marketScroll = ScrollView(this).apply { addView(list) }
        outer.addView(marketScroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 205))

        outer.addView(text("2. MODE TRADING", 14f, true), margin(0, 6, 0, 0))
        val modeSpinner = Spinner(this)
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        modeSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, modes)
        modeSpinner.setSelection(modes.indexOf(riskPrefs.getString("mode", "BALANCED")).coerceAtLeast(0))
        outer.addView(modeSpinner)

        outer.addView(text("3. DASAR PEMANTAUAN TP / SL", 14f, true), margin(0, 6, 0, 0))
        val basisGroup = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        val entryRadio = RadioButton(this).apply { text = "Harga ENTRY COIN — TP/SL mengikuti harga entry posisi" }
        val capitalRadio = RadioButton(this).apply { text = "MODAL BELI PERTAMA — target/rugi IDR dihitung dari modal pertama coin" }
        basisGroup.addView(entryRadio)
        basisGroup.addView(capitalRadio)
        val savedBasis = riskPrefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name)
        basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        entryRadio.id = View.generateViewId()
        capitalRadio.id = View.generateViewId()
        basisGroup.removeAllViews()
        basisGroup.addView(entryRadio)
        basisGroup.addView(capitalRadio)
        basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        outer.addView(basisGroup)
        outer.addView(text("Pada mode MODAL BELI PERTAMA, tiap coin memakai modal pada baris coin sebagai acuan. Contoh Rp50.000 tetap Rp50.000 walaupun harga entry berbeda.", 12f))

        outer.addView(text("4. TP / SL", 14f, true), margin(0, 6, 0, 0))
        val manualSwitch = Switch(this).apply { text = "TP / SL MANUAL"; isChecked = riskPrefs.getBoolean("manual_risk", false) }
        outer.addView(manualSwitch)
        val riskFields = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val slField = EditText(this).apply { hint = "SL %"; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(riskPrefs.getString("manual_sl", "0.50")) }
        val tpField = EditText(this).apply { hint = "TP %"; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(riskPrefs.getString("manual_tp", "1.00")) }
        riskFields.addView(slField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 8 })
        riskFields.addView(tpField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        riskFields.visibility = if (manualSwitch.isChecked) View.VISIBLE else View.GONE
        manualSwitch.setOnCheckedChangeListener { _, checked -> riskFields.visibility = if (checked) View.VISIBLE else View.GONE }
        outer.addView(riskFields)
        outer.addView(card("Decision Mode: SUGGESTION\nMirei tetap memegang gate risiko, freshness, posisi, fee/slippage. Re-entry tidak dipaksa.", 12f))

        val dialog = AlertDialog.Builder(this)
            .setTitle("MULAI SESI PAPER")
            .setMessage("Konfigurasi sesi sebelum runtime dimulai.")
            .setView(outer)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("MULAI", null)
            .create()
        dialog.setOnShowListener {
            dialog.window?.setLayout((resources.displayMetrics.widthPixels * 0.94f).toInt(), (resources.displayMetrics.heightPixels * 0.82f).toInt())
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val selected = rows.mapNotNull { (market, pair) ->
                    val (check, amount) = pair
                    if (!check.isChecked) null else amount.text.toString().toDoubleOrNull()?.takeIf { it > 0.0 }?.let { market to it }
                }
                if (selected.isEmpty() || selected.size > 3) { dialog.setMessage("Pilih minimal 1 dan maksimal 3 coin, dengan modal > 0."); return@setOnClickListener }
                val total = selected.sumOf { it.second }
                if (total > 150_000.0 + 1e-6) { dialog.setMessage("Total modal Rp ${numberFormat.format(total)} melebihi Rp150.000."); return@setOnClickListener }
                val manual = manualSwitch.isChecked
                val sl = slField.text.toString().toDoubleOrNull()
                val tp = tpField.text.toString().toDoubleOrNull()
                if (manual && (sl == null || tp == null || sl <= 0.0 || tp <= sl)) { dialog.setMessage("TP manual harus lebih besar dari SL manual dan keduanya harus > 0."); return@setOnClickListener }
                val mode = modeSpinner.selectedItem.toString()
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                riskPrefs.edit()
                    .putString("mode", mode)
                    .putBoolean("manual_risk", manual)
                    .putString("manual_sl", (sl ?: 0.50).toString())
                    .putString("manual_tp", (tp ?: 1.00).toString())
                    .putString("risk_basis", basisMode.name)
                    .apply()
                val allocations = selected.joinToString(";") { "${it.first}=${it.second}" }
                send(MireiForegroundService.ACTION_START) {
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations)
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, selected.first().first)
                    putExtra(MireiForegroundService.EXTRA_EXCHANGE, "indodax")
                }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun showRiskDialog() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 4, 12, 4) }
        box.addView(text("MODE TRADING", 14f, true))
        val modeSpinner = Spinner(this)
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        modeSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, modes)
        modeSpinner.setSelection(modes.indexOf(riskPrefs.getString("mode", "BALANCED")).coerceAtLeast(0))
        box.addView(modeSpinner)
        box.addView(text("DASAR PEMANTAUAN TP / SL", 14f, true), margin(0, 6, 0, 0))
        val basisGroup = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        val entryRadio = RadioButton(this).apply { id = View.generateViewId(); text = "Harga ENTRY COIN" }
        val capitalRadio = RadioButton(this).apply { id = View.generateViewId(); text = "MODAL BELI PERTAMA" }
        basisGroup.addView(entryRadio)
        basisGroup.addView(capitalRadio)
        val savedBasis = riskPrefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name)
        basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        box.addView(card("MODAL BELI PERTAMA memakai nominal modal pada saat coin pertama kali dialokasikan. Default contoh: Rp50.000/coin.", 12f))
        box.addView(basisGroup)

        box.addView(text("TP / SL MANUAL", 14f, true), margin(0, 6, 0, 0))
        val manualSwitch = Switch(this).apply { text = "Aktifkan override persen TP/SL"; isChecked = riskPrefs.getBoolean("manual_risk", false) }
        box.addView(manualSwitch)
        val fields = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val sl = EditText(this).apply { hint = "SL %"; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(riskPrefs.getString("manual_sl", "0.50")) }
        val tp = EditText(this).apply { hint = "TP %"; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(riskPrefs.getString("manual_tp", "1.00")) }
        fields.addView(sl, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 8 })
        fields.addView(tp, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        fields.visibility = if (manualSwitch.isChecked) View.VISIBLE else View.GONE
        manualSwitch.setOnCheckedChangeListener { _, checked -> fields.visibility = if (checked) View.VISIBLE else View.GONE }
        box.addView(fields)
        box.addView(card("Trailing: aktif sekitar 1R. Sistem hanya boleh menaikkan stop setelah profit mencapai aktivasi; tidak boleh melonggarkan stop.", 12.5f))
        val dialog = AlertDialog.Builder(this).setTitle("MODE & TP / SL").setMessage("Pilih dasar pemantauan terlebih dahulu.").setView(box).setNegativeButton("BATAL", null).setPositiveButton("SIMPAN", null).create()
        dialog.setOnShowListener {
            dialog.window?.setLayout((resources.displayMetrics.widthPixels * 0.92f).toInt(), (resources.displayMetrics.heightPixels * 0.58f).toInt())
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val manual = manualSwitch.isChecked
                val slValue = sl.text.toString().toDoubleOrNull()
                val tpValue = tp.text.toString().toDoubleOrNull()
                if (manual && (slValue == null || tpValue == null || slValue <= 0.0 || tpValue <= slValue)) { dialog.setMessage("TP manual harus > SL manual dan keduanya > 0."); return@setOnClickListener }
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                riskPrefs.edit()
                    .putString("mode", modeSpinner.selectedItem.toString())
                    .putBoolean("manual_risk", manual)
                    .putString("manual_sl", (slValue ?: 0.50).toString())
                    .putString("manual_tp", (tpValue ?: 1.00).toString())
                    .putString("risk_basis", basisMode.name)
                    .apply()
                send(MireiForegroundService.ACTION_APPLY_RISK)
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun requestRefresh() { send(MireiForegroundService.ACTION_REFRESH) }

    private fun send(action: String, extras: Intent.() -> Unit = {}) {
        val intent = Intent(this, MireiForegroundService::class.java).apply { this.action = action; extras() }
        runCatching { if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }
            .onFailure { AlertDialog.Builder(this).setTitle("Mirei").setMessage("Perintah tidak dapat dijalankan: ${it.message ?: "error"}").setPositiveButton("OK", null).show() }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100)
    }

    private fun stateLabel(state: String): String = when (state) { "RUNNING" -> "BERJALAN"; "HOLD" -> "JEDA / HOLD"; else -> "BERHENTI" }
    private fun modeLabel(mode: String): String = when (mode) { "AGGRESSIVE" -> "AGRESIF"; "SAFETY" -> "AMAN"; else -> "SEIMBANG" }
    private fun riskBasisLabel(raw: String): String = when (raw) { RiskReferenceMode.INITIAL_CAPITAL.name -> "MODAL BELI PERTAMA"; else -> "HARGA ENTRY COIN" }
    private fun sessionClock(i: Intent): String {
        val start = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STARTED, 0L)
        val stop = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STOPPED, 0L)
        if (start <= 0L) return "BELUM DIMULAI"
        val active = i.getStringExtra(MireiForegroundService.EXTRA_STATE) == "RUNNING"
        val end = if (active) System.currentTimeMillis() else stop.takeIf { it > 0L } ?: System.currentTimeMillis()
        val duration = (end - start).coerceAtLeast(0L) / 1000L
        return "${duration / 60}m ${duration % 60}s · ${formatClock(start)} → ${if (active) "BERJALAN" else formatClock(end)}"
    }

    private fun clockCard(i: Intent): TextView {
        val start = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STARTED, 0L)
        val stop = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STOPPED, 0L)
        val reset = i.getLongExtra(MireiForegroundService.EXTRA_CLOCK_RESET, 0L)
        return card("MULAI: ${if (start > 0L) formatClock(start) else "—"}\nSTOP / JEDA / CLOSE: ${if (stop > 0L) formatClock(stop) else "—"}\nRESET TIMESTAMP: ${if (reset > 0L) formatClock(reset) else "—"}\nFORMAT: MM//DD//HH/MM", 13f)
    }

    private fun formatAge(openedAt: Long): String {
        val seconds = ((System.currentTimeMillis() - openedAt).coerceAtLeast(0L)) / 1000L
        return "${seconds / 60}m ${seconds % 60}s"
    }

    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { line ->
        line.split('|').mapNotNull { token -> val idx = token.indexOf('='); if (idx > 0) token.substring(0, idx) to token.substring(idx + 1) else null }.toMap() + mapOf("symbol" to line.substringBefore('|'))
    }

    private fun humanReason(raw: String): String = raw.replace('_', ' ').replace("agent conflict requires human decision", "agent berbeda; perlu verifikasi manusia").replace("no decision", "belum ada keputusan")
    private fun humanReasons(raw: String): String = raw.ifBlank { "Tidak ada gate yang tercatat." }.split("|").joinToString("\n") { "• ${it.trim().replace('_', ' ')}" }
    private fun humanEntryReason(raw: String): String = when (raw) { "initial_holding" -> "HOLDING AWAL"; "re_entry", "human_verified_re_entry" -> "MASUK KEMBALI"; "human_verified_entry" -> "ENTRY · VERIFIKASI MANUSIA"; else -> "ENTRY OTOMATIS" }
    private fun humanExitReason(raw: String?): String = when (raw) { "stop_loss" -> "BATAS RUGI"; "take_profit" -> "AMBIL PROFIT"; "ai_close" -> "KELUAR OLEH STRATEGI"; "manual_close_all" -> "TUTUP MANUAL"; else -> raw?.replace('_', ' ') ?: "—" }
    private fun humanEventType(raw: String): String = when (raw) { "SL_CLOSE" -> "BATAS RUGI"; "TP_CLOSE" -> "AMBIL PROFIT"; "RE_ENTRY" -> "MASUK KEMBALI"; "OPEN" -> "OPEN"; "MANUAL_CLOSE" -> "TUTUP MANUAL"; "HUMAN_VERIFIED_ENTRY" -> "ENTRY VERIFIKASI MANUSIA"; "SESSION_STOPPED" -> "SESI BERHENTI"; "SESSION_PAUSED" -> "SESI JEDA"; "SESSION_CLOSED" -> "SEMUA POSISI DITUTUP"; else -> raw.replace('_', ' ') }
    private fun humanAgent(raw: String): String = when (raw) { "MARKET" -> "MARKET / MOMENTUM"; "CANDLE" -> "CANDLE"; "FORECAST" -> "FORECAST"; "SENTIMENT" -> "SENTIMENT"; else -> raw }
    private fun signedMoney(value: Double): String = if (value >= 0) "+${numberFormat.format(value)}" else "-${numberFormat.format(kotlin.math.abs(value))}"
    private fun signed(value: Double): String = if (value >= 0) "+%.3f".format(Locale.US, value) else "%.3f".format(Locale.US, value)
    private fun fmt(value: Double): String = "%.3f".format(Locale.US, value)
    private fun formatEpoch(epoch: Long): String = if (epoch <= 0L) "—" else SimpleDateFormat("MM/dd HH:mm:ss", Locale.US).format(Date(epoch))
    private fun formatClock(epoch: Long): String = if (epoch <= 0L) "—" else SimpleDateFormat("MM'//'dd'//'HH/mm", Locale.US).format(Date(epoch))
    private fun addTitle(value: String) { content.addView(text(value, 20f, true), margin(0, 8, 0, 6)) }
    private fun text(value: String, size: Float, bold: Boolean = false): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(Color.WHITE); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(6, 4, 6, 4) }
    private fun card(value: String, size: Float = 15f): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(10, 10, 10, 10); setBackgroundColor(Color.rgb(24, 34, 43)) }.also { it.layoutParams = margin(0, 4, 0, 6) }
    private fun button(label: String, onClick: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { onClick() }; layoutParams = margin(0, 4, 0, 6) }
    private fun weight(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 4 }
    private fun margin(l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }
}

private class MiniMarketChartView(context: Context, private val values: FloatArray) : View(context) {
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.CYAN; strokeWidth = 5f; style = Paint.Style.STROKE }
    private val zeroPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.GRAY; strokeWidth = 2f }
    private val pointPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.FILL }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = MeasureSpec.getSize(widthMeasure)
        setMeasuredDimension(width, 180)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.rgb(24, 34, 43))
        if (values.isEmpty()) return
        val left = 18f
        val right = width - 18f
        val centerY = height / 2f
        val maxAbs = values.maxOf { kotlin.math.abs(it) }.coerceAtLeast(0.01f)
        canvas.drawLine(left, centerY, right, centerY, zeroPaint)
        val path = Path()
        values.forEachIndexed { index, value ->
            val x = if (values.size == 1) (left + right) / 2f else left + (right - left) * index / (values.size - 1).toFloat()
            val y = centerY - (value / maxAbs) * (height * 0.38f)
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
            canvas.drawCircle(x, y, 6f, pointPaint)
        }
        canvas.drawPath(path, linePaint)
    }
}
