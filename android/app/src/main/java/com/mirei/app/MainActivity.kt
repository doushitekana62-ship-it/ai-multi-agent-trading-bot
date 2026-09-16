package com.mirei.app

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var content: LinearLayout
    private lateinit var statusCard: TextView
    private val handler = Handler(Looper.getMainLooper())
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
    private val riskPrefs by lazy { getSharedPreferences("mirei_settings", MODE_PRIVATE) }
    private var currentIntent: Intent? = null
    private var currentMenu = Menu.RINGKASAN
    private var menuSpinner: Spinner? = null

    private enum class Menu(val label: String) { RINGKASAN("RINGKASAN"), PASAR("PASAR"), POSISI("POSISI"), AKTIVITAS("AKTIVITAS"), KEPUTUSAN("KEPUTUSAN"), RISIKO("RISIKO"), PENGATURAN("PENGATURAN"), AUDIT("LOG / AUDIT") }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != MireiForegroundService.ACTION_STATUS) return
            currentIntent = intent
            renderHeader(); renderCurrentMenu()
        }
    }

    private val clockRunnable = object : Runnable {
        override fun run() { renderHeader(); if (currentMenu == Menu.RINGKASAN) renderCurrentMenu(); handler.postDelayed(this, 1_000L) }
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

    override fun onStop() { runCatching { unregisterReceiver(receiver) }; super.onStop() }
    override fun onDestroy() { handler.removeCallbacksAndMessages(null); super.onDestroy() }

    private fun buildShell() {
        val shell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 14, 12, 18); setBackgroundColor(Color.rgb(48, 48, 48)) }
        shell.addView(text("Mirei", 30f, true))
        shell.addView(text("Asisten trading crypto · lokal · paper trading", 14f), margin(0, 2, 0, 8))
        statusCard = card("BERHENTI · PAPER ONLY")
        shell.addView(statusCard, margin(0, 0, 0, 8))
        shell.addView(text("MENU", 12f, true))
        val menu = Spinner(this); menuSpinner = menu
        menu.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, Menu.values().map { it.label })
        menu.setSelection(currentMenu.ordinal)
        menu.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { val selected = Menu.values().getOrNull(position) ?: return; if (selected != currentMenu) { currentMenu = selected; renderCurrentMenu() } }
        }
        shell.addView(menu, margin(0, 0, 0, 8))
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, 16) }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content, ViewGroup.LayoutParams(-1, -2)) }
        shell.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(shell); renderCurrentMenu()
    }

    private fun renderHeader() {
        val i = currentIntent ?: run { statusCard.text = "BERHENTI · PAPER ONLY\nBelum ada status runtime."; return }
        val state = when (i.getStringExtra(MireiForegroundService.EXTRA_STATE)) { "RUNNING" -> "BERJALAN"; "HOLD" -> "JEDA / HOLD"; else -> "BERHENTI" }
        val equity = i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0); val cash = i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0); val positions = i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        statusCard.text = "$state · PAPER ONLY · ${i.getStringExtra(MireiForegroundService.EXTRA_EXCHANGE)?.uppercase(Locale.US) ?: "INDODAX"}\nNilai Rp ${numberFormat.format(equity)} · Kas Rp ${numberFormat.format(cash)} · Posisi $positions\nWaktu sesi: ${sessionClock(i)}"
    }

    private fun renderCurrentMenu() {
        content.removeAllViews(); menuSpinner?.setSelection(currentMenu.ordinal, false)
        runCatching { when (currentMenu) { Menu.RINGKASAN -> renderSummary(); Menu.PASAR -> renderMarket(); Menu.POSISI -> renderPositions(); Menu.AKTIVITAS -> renderActivity(); Menu.KEPUTUSAN -> renderDecision(); Menu.RISIKO -> renderRisk(); Menu.PENGATURAN -> renderSettings(); Menu.AUDIT -> renderAudit() } }.onFailure { content.addView(card("UI error: ${it.message ?: "unknown"}")) }
    }

    private fun renderSummary() {
        addTitle("DASHBOARD · RINGKASAN")
        val i = currentIntent
        if (i == null) { content.addView(card("Belum ada data runtime.")); addControls(); return }
        val buys = i.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0); val holds = i.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0); val sells = i.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0); val positions = i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        val maxPositions = 3
        val executionNote = if (positions >= maxPositions && buys > 0) "AI OPEN = keputusan analisis. ACTUAL OPEN = 0 pada tick karena kapasitas posisi ${positions}/${maxPositions} sudah penuh oleh holding aktif. Ini bukan order yang hilang." else "AI OPEN dan ACTUAL OPEN dipisahkan: keputusan AI belum tentu lolos gate eksekusi."
        content.addView(card("STATUS\n${stateLabel(i.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP")}\n\nMODAL AWAL\nRp ${numberFormat.format(150000.0)}\n\nNILAI AKUN\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n\nKAS TERSEDIA\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n\nPnL TEREALISASI\nRp ${signedMoney(i.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0))}\n\nPOSISI\n$positions/$maxPositions", 14f))
        addTitle("AI VS ACTUAL · SESI INI")
        content.addView(card("SUMBER                 BUY/OPEN   HOLD/ACTIVE   SELL/CLOSE\nAI DECISION             $buys        $holds          $sells\nACTUAL PAPER            —          $positions         —\n\n$executionNote\n\nACTUAL PAPER hanya bertambah ketika engine benar-benar membuka posisi. Holding awal dihitung sebagai posisi nyata.", 13f))
        addTitle("EVENT TERAKHIR")
        content.addView(card(i.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Belum ada OPEN/CLOSE pada tick terakhir." }, 13f))
        addTitle("KEPUTUSAN TERAKHIR")
        content.addView(card("${i.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"} · ${(i.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()}%\n${humanReason(i.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty())}", 13f))
        addControls()
    }

    private fun addControls() {
        addTitle("KONTROL SESI")
        val r1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        r1.addView(button("MULAI") { showStartDialog() }, weight()); r1.addView(button("SEGARKAN DATA") { requestRefresh() }, weight())
        content.addView(r1)
        val r2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        r2.addView(button("JEDA / HOLD") { send(MireiForegroundService.ACTION_HOLD) }, weight()); r2.addView(button("BERHENTI") { send(MireiForegroundService.ACTION_STOP) }, weight())
        content.addView(r2)
        content.addView(button("TUTUP SEMUA POSISI") { send(MireiForegroundService.ACTION_CLOSE_ALL) })
    }

    private fun renderMarket() {
        addTitle("PASAR")
        val i = currentIntent ?: run { content.addView(card("Belum ada snapshot pasar.")); return }
        val symbol = i.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: "BTC/IDR"
        content.addView(card("$symbol\nHarga Rp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0))}\n1M ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0))}% · 5M ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0))}% · 15M ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0))}%\nMomentum ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0))}% · Trend ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0))}%\nFlow ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0))}% · Forecast ${(i.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0) * 100).toInt()}%\nSpread ${fmt(i.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0))}%\nData ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}", 14f))
        addTitle("SCANNER")
        val rows = i.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty().lines().filter { it.isNotBlank() }.take(10)
        if (rows.isEmpty()) content.addView(card("Belum ada hasil scanner.")) else rows.forEach { line -> val p = line.split('|'); if (p.size >= 8) content.addView(card("${p[0]} · ${p[1]} · ${p[2]}\nHarga Rp ${p[3]}\n1M ${p[4]}% · Momentum ${p[5]}% · Trend ${p[6]}% · Volume ${p[7]}%", 12.5f)) }
    }

    private fun renderPositions() {
        addTitle("POSISI AKTIF")
        val rows = parsePositions(currentIntent?.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        if (rows.isEmpty()) { content.addView(card("Tidak ada posisi aktif.")); return }
        rows.forEach { row -> content.addView(card("${row["symbol"].orEmpty()}\nModal Rp ${numberFormat.format(row["stake"].orEmpty().toDoubleOrNull() ?: 0.0)}\nEntry Rp ${numberFormat.format(row["entry"].orEmpty().toDoubleOrNull() ?: 0.0)}\nSekarang Rp ${numberFormat.format(row["current"].orEmpty().toDoubleOrNull() ?: 0.0)}\nPnL belum terealisasi Rp ${signedMoney(row["unrealized"].orEmpty().toDoubleOrNull() ?: 0.0)}\n\nTP Rp ${numberFormat.format(row["tp"].orEmpty().toDoubleOrNull() ?: 0.0)}\nSL Rp ${numberFormat.format(row["sl"].orEmpty().toDoubleOrNull() ?: 0.0)}\nDasar: ${riskBasisLabel(row["risk_basis"].orEmpty())}\nModal acuan: Rp ${numberFormat.format(row["risk_capital"].orEmpty().toDoubleOrNull() ?: 0.0)}\nAsal: ${row["entry_reason"].orEmpty()}", 13.5f)) }
    }

    private fun renderActivity() {
        addTitle("AKTIVITAS · SESI INI")
        val start = currentIntent?.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L) ?: 0L
        runCatching {
            val db = MireiDatabase(this); val trades = db.recentTrades(100).filter { start == 0L || it.openedAtEpochMs >= start }; val audits = db.recentAudit(150).filter { start == 0L || it.createdAtEpochMs >= start }
            if (trades.isEmpty() && audits.isEmpty()) content.addView(card("Belum ada transaksi pada sesi ini."))
            trades.forEach { t -> content.addView(card("${formatEpoch(t.openedAtEpochMs)} · ${t.symbol}\n${t.entryReason}\nStatus ${t.status}\nEntry Rp ${numberFormat.format(t.entryPrice ?: 0.0)}\nExit ${t.exitPrice?.let { "Rp ${numberFormat.format(it)}" } ?: "—"}\nPnL ${signedMoney(t.pnlIdr)}", 12.5f)) }
            audits.filter { it.eventType in setOf("OPEN", "RE_ENTRY", "SL_CLOSE", "TP_CLOSE", "MANUAL_CLOSE", "HUMAN_VERIFIED_ENTRY", "SESSION_STOPPED", "SESSION_PAUSED", "SESSION_CLOSED", "RUNTIME_ERROR") }.forEach { e -> content.addView(card("${formatEpoch(e.createdAtEpochMs)} · ${e.eventType}\n${e.details.replace('|', '\n').replace('_', ' ')}", 12f)) }
        }.onFailure { content.addView(card("Riwayat tidak dapat dibaca: ${it.message ?: "database error"}")) }
    }

    private fun renderDecision() {
        addTitle("KEPUTUSAN")
        val i = currentIntent ?: run { content.addView(card("Belum ada keputusan.")); return }
        content.addView(card("${i.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"} · ${(i.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()}%\n\n${humanReason(i.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty())}\n\nGate: ${i.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty().replace('|', '\n')}", 13.5f))
        content.addView(card("BUY ${i.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)}\nHOLD ${i.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)}\nSELL ${i.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)}", 13.5f))
    }

    private fun renderRisk() {
        addTitle("RISIKO / TRADE TYPE")
        val profiles = riskPrefs.getString("position_profiles", "").orEmpty()
        content.addView(card("Konfigurasi per instrument tersimpan: ${if (profiles.isBlank()) "belum ada" else "YA"}\nMode sesi lama: ${riskPrefs.getString("mode", "BALANCED")}\nDasar sesi: ${riskBasisLabel(riskPrefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name) ?: "")}", 13.5f))
        content.addView(button("ATUR JENIS TRADE PER INSTRUMENT") { showStartDialog() })
        content.addView(button("TERAPKAN RISIKO") { send(MireiForegroundService.ACTION_APPLY_RISK) })
        content.addView(card("Setiap posisi menyimpan TP/SL dan profilnya sendiri. Re-entry tidak boleh langsung pada tick close; cooldown minimum 1 detik dan re-entry dijadwalkan pada market tick berikutnya.", 12.5f))
    }

    private fun renderSettings() {
        addTitle("PENGATURAN")
        content.addView(card("Decision Mode: SUGGESTION\nPaper only\nMaksimum posisi: 3\nBatas modal sesi: Rp150.000\nPer-trade TP/SL: konfigurasi melalui MULAI / ATUR JENIS TRADE PER INSTRUMENT.", 13.5f))
        content.addView(button("KONFIGURASI SESI / JENIS TRADE") { showStartDialog() })
        content.addView(button("RESET TIMESTAMP") { send(MireiForegroundService.ACTION_RESET_CLOCK) })
        content.addView(button("SESI PAPER BARU") { AlertDialog.Builder(this).setTitle("Sesi paper baru").setMessage("Portfolio sesi aktif akan direset. Riwayat database tetap ada.").setNegativeButton("BATAL", null).setPositiveButton("RESET") { _, _ -> send(MireiForegroundService.ACTION_RESET_SESSION) }.show() })
    }

    private fun renderAudit() {
        addTitle("LOG / AUDIT · SESI INI")
        val start = currentIntent?.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L) ?: 0L
        runCatching { MireiDatabase(this).recentAudit(200).filter { start == 0L || it.createdAtEpochMs >= start }.forEach { e -> content.addView(card("${formatEpoch(e.createdAtEpochMs)} · ${e.eventType}\n${e.details.replace('|', '\n').replace('_', ' ')}", 12f)) } }.onFailure { content.addView(card("Log tidak dapat dibaca: ${it.message ?: "database error"}")) }
    }

    private fun showStartDialog() { MireiStartSessionDialog.show(this) }
    private fun requestRefresh() { send(MireiForegroundService.ACTION_REFRESH) }
    private fun send(action: String, extras: Intent.() -> Unit = {}) { val intent = Intent(this, MireiForegroundService::class.java).apply { this.action = action; extras() }; runCatching { if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }.onFailure { AlertDialog.Builder(this).setTitle("Mirei").setMessage(it.message ?: "Perintah gagal").setPositiveButton("OK", null).show() } }
    private fun requestNotificationPermissionIfNeeded() { if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100) }
    private fun stateLabel(state: String): String = when (state) { "RUNNING" -> "BERJALAN"; "HOLD" -> "JEDA / HOLD"; else -> "BERHENTI" }
    private fun riskBasisLabel(raw: String): String = if (raw == RiskReferenceMode.INITIAL_CAPITAL.name) "MODAL BELI PERTAMA" else "HARGA ENTRY"
    private fun humanReason(raw: String): String = raw.ifBlank { "Belum ada keputusan." }.replace('_', ' ')
    private fun signedMoney(value: Double): String = if (value >= 0.0) "+${numberFormat.format(value)}" else "-${numberFormat.format(kotlin.math.abs(value))}"
    private fun signed(value: Double): String = if (value >= 0.0) "+%.3f".format(Locale.US, value) else "%.3f".format(Locale.US, value)
    private fun fmt(value: Double): String = "%.3f".format(Locale.US, value)
    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { line -> line.split('|').mapNotNull { token -> val p = token.indexOf('='); if (p > 0) token.substring(0, p) to token.substring(p + 1) else null }.toMap() + mapOf("symbol" to line.substringBefore('|')) }
    private fun sessionClock(i: Intent): String { val start = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STARTED, 0L); if (start <= 0L) return "BELUM DIMULAI"; val active = i.getStringExtra(MireiForegroundService.EXTRA_STATE) == "RUNNING"; val stop = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STOPPED, 0L); val end = if (active) System.currentTimeMillis() else stop.takeIf { it > 0L } ?: System.currentTimeMillis(); val seconds = ((end - start).coerceAtLeast(0L) / 1000L); return "${seconds / 60}m ${seconds % 60}s · ${formatClock(start)} → ${if (active) "BERJALAN" else formatClock(end)}" }
    private fun formatClock(epoch: Long): String = SimpleDateFormat("MM/dd/HH:mm", Locale.US).format(Date(epoch))
    private fun formatEpoch(epoch: Long): String = if (epoch <= 0L) "—" else SimpleDateFormat("MM/dd HH:mm:ss", Locale.US).format(Date(epoch))
    private fun addTitle(value: String) { content.addView(text(value, 20f, true), margin(0, 8, 0, 6)) }
    private fun text(value: String, size: Float, bold: Boolean = false): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(Color.WHITE); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(6, 4, 6, 4) }
    private fun card(value: String, size: Float = 15f): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(10, 10, 10, 10); setBackgroundColor(Color.rgb(24, 34, 43)) }.also { it.layoutParams = margin(0, 4, 0, 6) }
    private fun button(label: String, onClick: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { onClick() }; layoutParams = margin(0, 4, 0, 6) }
    private fun weight(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 4 }
    private fun margin(l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }
}
