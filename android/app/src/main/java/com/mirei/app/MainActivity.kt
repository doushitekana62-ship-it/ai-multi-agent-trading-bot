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
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.mirei.app.core.PositionTradeConfigStore
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
    private val prefs by lazy { getSharedPreferences("mirei_settings", MODE_PRIVATE) }
    private var currentIntent: Intent? = null
    private var currentTab = Tab.RINGKASAN
    private var tabsLayout: LinearLayout? = null

    private enum class Tab(val label: String) { RINGKASAN("RINGKASAN"), POSISI("POSISI"), PASAR("PASAR"), AUDIT("LOG AUDIT") }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != MireiForegroundService.ACTION_STATUS) return
            currentIntent = intent
            renderHeader()
            renderCurrentTab()
        }
    }

    private val clockRunnable = object : Runnable {
        override fun run() {
            renderHeader()
            if (currentTab == Tab.RINGKASAN) renderCurrentTab()
            handler.postDelayed(this, 1_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        PositionTradeConfigStore.reload(this)
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
        val shell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(10, 10, 10, 14); setBackgroundColor(Color.rgb(48, 48, 48)) }
        shell.addView(text("Mirei", 30f, true))
        shell.addView(text("Asisten trading · lokal · paper trading", 14f), margin(0, 0, 0, 6))
        statusCard = card("BERHENTI · PAPER ONLY")
        shell.addView(statusCard, margin(0, 0, 0, 6))
        tabsLayout = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        shell.addView(tabsLayout, margin(0, 0, 0, 6))
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, 16) }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content, ViewGroup.LayoutParams(-1, -2)) }
        shell.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(shell)
        renderTabs()
        renderCurrentTab()
    }

    private fun renderTabs() {
        val tabs = tabsLayout ?: return
        tabs.removeAllViews()
        Tab.values().forEach { tab ->
            val b = button(tab.label) { currentTab = tab; renderTabs(); renderCurrentTab() }
            b.textSize = 11f
            b.isAllCaps = false
            if (tab == currentTab) b.setBackgroundColor(Color.rgb(88, 88, 88))
            tabs.addView(b, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 3 })
        }
    }

    private fun renderHeader() {
        val i = currentIntent ?: run { statusCard.text = "BERHENTI · PAPER ONLY\nBelum ada status runtime."; return }
        val state = when (i.getStringExtra(MireiForegroundService.EXTRA_STATE)) { "RUNNING" -> "BERJALAN"; "HOLD" -> "JEDA / HOLD"; else -> "BERHENTI" }
        val equity = i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val cash = i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val positions = i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        statusCard.text = "$state · PAPER ONLY · ${i.getStringExtra(MireiForegroundService.EXTRA_EXCHANGE)?.uppercase(Locale.US) ?: "INDODAX"}\nNilai Rp ${numberFormat.format(equity)} · Kas Rp ${numberFormat.format(cash)} · Posisi $positions\nWaktu sesi: ${sessionClock(i)}"
    }

    private fun renderCurrentTab() {
        content.removeAllViews()
        runCatching {
            when (currentTab) {
                Tab.RINGKASAN -> renderSummary()
                Tab.POSISI -> renderPositions()
                Tab.PASAR -> renderMarket()
                Tab.AUDIT -> renderAudit()
            }
        }.onFailure { content.addView(card("UI error: ${it.message ?: "unknown"}")) }
    }

    private fun renderSummary() {
        addTitle("DASHBOARD · RINGKASAN")
        val i = currentIntent
        if (i == null) { content.addView(card("Belum ada snapshot runtime.")); addControls(); return }
        val positions = i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        val buys = i.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)
        val holds = i.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)
        val sells = i.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)
        val profiles = PositionTradeConfigStore.snapshot()
        content.addView(card("STATUS\n${stateLabel(i.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP")}\n\nMODAL SESI\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_TOTAL_CAPITAL, 150000.0))}\n\nEQUITY\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n\nKAS\nRp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n\nPnL TEREALISASI\nRp ${signedMoney(i.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0))}\n\nPOSISI\n$positions/3", 14f))
        addTitle("AI VS ACTUAL · SESI INI")
        content.addView(card("AI DECISION  · BUY $buys · HOLD $holds · SELL $sells\nACTUAL PAPER · posisi aktif $positions\n\nAI OPEN adalah keputusan analisis. ACTUAL OPEN hanya bertambah setelah execution gate benar-benar berhasil.", 13f))
        addTitle("PENGATURAN AKTIF")
        if (profiles.isEmpty()) content.addView(card("Belum ada kontrak instrument tersimpan."))
        else profiles.forEach { (symbol, profile) -> content.addView(card("$symbol\nMode: ${profile.mode?.name ?: "BALANCED"}\nTP/SL: ${if (profile.manualRiskMode.name == "MANUAL") "MANUAL" else "AUTO"}\nTP: ${profile.manualNetProfitTargetIdr?.let { "NET Rp${numberFormat.format(it)}" } ?: profile.manualTakeProfitPercent?.let { "${it}%" } ?: "mengikuti mode"}\nSL: ${profile.stopLossPercent?.let { "${it}%" } ?: "mengikuti mode"}\nDasar: ${profile.riskReferenceMode?.let { riskBasisLabel(it.name) } ?: "HARGA ENTRY"}", 12.5f)) }
        addControls()
    }

    private fun addControls() {
        addTitle("KONTROL SESI")
        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row1.addView(button("MULAI") { showStartDialog() }, weight())
        row1.addView(button("LANJUTKAN") { send(MireiForegroundService.ACTION_START) }, weight())
        row1.addView(button("SEGARKAN DATA") { requestRefresh() }, weight())
        content.addView(row1)
        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row2.addView(button("JEDA / HOLD") { send(MireiForegroundService.ACTION_HOLD) }, weight())
        row2.addView(button("BERHENTI") { send(MireiForegroundService.ACTION_STOP) }, weight())
        content.addView(row2)
        content.addView(button("TUTUP SEMUA POSISI") { send(MireiForegroundService.ACTION_CLOSE_ALL) })
        content.addView(button("PENGATURAN / MARKET SELECTION") { showStartDialog() })
    }

    private fun renderPositions() {
        addTitle("POSISI AKTIF")
        val rows = parsePositions(currentIntent?.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        if (rows.isEmpty()) { content.addView(card("Tidak ada posisi aktif.")); return }
        rows.forEach { row ->
            val symbol = row["symbol"].orEmpty()
            val profile = PositionTradeConfigStore.get(symbol)
            val tpMode = profile?.manualNetProfitTargetIdr?.let { "MANUAL NET Rp${numberFormat.format(it)}" }
                ?: profile?.manualTakeProfitPercent?.let { "MANUAL ${it}%" }
                ?: "AUTO/MODE"
            content.addView(card("$symbol\nModal Rp ${numberFormat.format(row["stake"].orEmpty().toDoubleOrNull() ?: 0.0)}\nEntry Rp ${numberFormat.format(row["entry"].orEmpty().toDoubleOrNull() ?: 0.0)}\nSekarang Rp ${numberFormat.format(row["current"].orEmpty().toDoubleOrNull() ?: 0.0)}\nPnL berjalan Rp ${signedMoney(row["unrealized"].orEmpty().toDoubleOrNull() ?: 0.0)}\n\nTP Rp ${numberFormat.format(row["tp"].orEmpty().toDoubleOrNull() ?: 0.0)} · $tpMode\nSL Rp ${numberFormat.format(row["sl"].orEmpty().toDoubleOrNull() ?: 0.0)}\nDasar: ${riskBasisLabel(row["risk_basis"].orEmpty())}\nAsal: ${row["entry_reason"].orEmpty()}", 13f))
        }
    }

    private fun renderMarket() {
        addTitle("PASAR")
        val i = currentIntent ?: run { content.addView(card("Belum ada snapshot pasar.")); return }
        val symbol = i.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: "BTC/IDR"
        content.addView(card("INSTRUMENT AKTIF\n$symbol · ${i.getStringExtra(MireiForegroundService.EXTRA_EXCHANGE)?.uppercase(Locale.US) ?: "INDODAX"}\nHarga Rp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0))}\nBid Rp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_BID, 0.0))} · Ask Rp ${numberFormat.format(i.getDoubleExtra(MireiForegroundService.EXTRA_ASK, 0.0))}\nSpread ${fmt(i.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0))}%\n1M ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0))}% · 5M ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0))}% · 15M ${signed(i.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0))}%\nData ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"} · age ${i.getLongExtra(MireiForegroundService.EXTRA_SOURCE_AGE, 0L)}ms", 13f))
        addTitle("SCANNER")
        val rows = i.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty().lines().filter { it.isNotBlank() }.take(12)
        if (rows.isEmpty()) content.addView(card("Belum ada hasil scanner."))
        rows.forEach { line ->
            val p = line.split('|')
            if (p.size >= 8) content.addView(card("${p[0]} · ${p[1]} · provider ${p[2]}\nHarga ${p[3]} · 1M ${p[4]}% · Momentum ${p[5]}% · Trend ${p[6]}% · Volume share ${p[7]}%", 12f))
        }
    }

    private fun renderAudit() {
        addTitle("LOG AUDIT · SESI INI")
        content.addView(card("Waktu | Simbol | Event | Harga/PnL | Alasan", 11f))
        val start = currentIntent?.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L) ?: 0L
        runCatching {
            val db = MireiDatabase(this)
            val trades = db.recentTrades(150).filter { start == 0L || it.openedAtEpochMs >= start }
            val audits = db.recentAudit(250).filter { start == 0L || it.createdAtEpochMs >= start }
            if (trades.isEmpty() && audits.isEmpty()) { content.addView(card("Belum ada event pada sesi ini.")); return@runCatching }
            val table = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            trades.forEach { trade ->
                addAuditRow(table, formatEpoch(trade.openedAtEpochMs), trade.symbol, trade.status, trade.exitPrice?.let { "Rp ${numberFormat.format(it)}" } ?: "Rp ${numberFormat.format(trade.entryPrice ?: 0.0)} / PnL ${signedMoney(trade.pnlIdr)}", trade.entryReason)
            }
            audits.forEach { event ->
                val details = event.details.replace('|', ' ')
                val symbol = details.substringAfter("symbol=", "—").substringBefore(' ')
                val pnl = details.substringAfter("pnl=", "").substringBefore(' ')
                val priceText = if (pnl.isNotBlank()) "PnL $pnl" else "—"
                addAuditRow(table, formatEpoch(event.createdAtEpochMs), symbol, event.eventType, priceText, details)
            }
            val horizontal = HorizontalScrollView(this).apply { addView(table) }
            content.addView(horizontal)
        }.onFailure { content.addView(card("Log tidak dapat dibaca: ${it.message ?: "database error"}")) }
    }

    private fun addAuditRow(table: LinearLayout, time: String, symbol: String, event: String, price: String, reason: String) {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(Color.rgb(24, 34, 43)) }
        listOf(time, symbol, event, price, reason).forEach { value -> row.addView(text(value, 10f), LinearLayout.LayoutParams(dp(118), ViewGroup.LayoutParams.WRAP_CONTENT)) }
        table.addView(row, margin(0, 1, 0, 1))
    }

    private fun showStartDialog() { MireiStartSessionDialog.show(this) }
    private fun requestRefresh() { send(MireiForegroundService.ACTION_REFRESH) }
    private fun send(action: String, extras: Intent.() -> Unit = {}) {
        val intent = Intent(this, MireiForegroundService::class.java).apply { this.action = action; extras() }
        runCatching { if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }.onFailure { AlertDialog.Builder(this).setTitle("Mirei").setMessage(it.message ?: "Perintah gagal").setPositiveButton("OK", null).show() }
    }
    private fun requestNotificationPermissionIfNeeded() { if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100) }
    private fun stateLabel(state: String): String = when (state) { "RUNNING" -> "BERJALAN"; "HOLD" -> "JEDA / HOLD"; else -> "BERHENTI" }
    private fun riskBasisLabel(raw: String): String = if (raw == RiskReferenceMode.INITIAL_CAPITAL.name) "MODAL BELI PERTAMA" else "HARGA ENTRY"
    private fun signedMoney(value: Double): String = if (value >= 0.0) "+${numberFormat.format(value)}" else "-${numberFormat.format(kotlin.math.abs(value))}"
    private fun signed(value: Double): String = if (value >= 0.0) "+%.3f".format(Locale.US, value) else "%.3f".format(Locale.US, value)
    private fun fmt(value: Double): String = "%.3f".format(Locale.US, value)
    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { line -> line.split('|').mapNotNull { token -> val p = token.indexOf('='); if (p > 0) token.substring(0, p) to token.substring(p + 1) else null }.toMap() + mapOf("symbol" to line.substringBefore('|')) }
    private fun sessionClock(i: Intent): String { val start = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STARTED, 0L); if (start <= 0L) return "BELUM DIMULAI"; val active = i.getStringExtra(MireiForegroundService.EXTRA_STATE) == "RUNNING"; val stop = i.getLongExtra(MireiForegroundService.EXTRA_RUN_STOPPED, 0L); val end = if (active) System.currentTimeMillis() else stop.takeIf { it > 0L } ?: System.currentTimeMillis(); val seconds = ((end - start).coerceAtLeast(0L) / 1000L); return "${seconds / 60}m ${seconds % 60}s · ${formatClock(start)} → ${if (active) "BERJALAN" else formatClock(end)}" }
    private fun formatClock(epoch: Long): String = SimpleDateFormat("MM/dd/HH:mm", Locale.US).format(Date(epoch))
    private fun formatEpoch(epoch: Long): String = if (epoch <= 0L) "—" else SimpleDateFormat("MM/dd HH:mm:ss", Locale.US).format(Date(epoch))
    private fun addTitle(value: String) { content.addView(text(value, 20f, true), margin(0, 8, 0, 5)) }
    private fun text(value: String, size: Float, bold: Boolean = false): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(Color.WHITE); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(5, 4, 5, 4) }
    private fun card(value: String, size: Float = 14f): TextView = TextView(this).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(9, 9, 9, 9); setBackgroundColor(Color.rgb(24, 34, 43) }.also { it.layoutParams = margin(0, 3, 0, 5) }
    private fun button(label: String, onClick: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { onClick() }; minHeight = dp(46); layoutParams = margin(0, 3, 3, 5) }
    private fun weight(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 3 }
    private fun margin(l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }
    private fun dp(value: Int): Int = (value * resources.displayMetrics.density + 0.5f).toInt()
}
