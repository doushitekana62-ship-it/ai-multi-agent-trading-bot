package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.app.Application
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
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
import com.mirei.app.runtime.IndodaxMarketDataSource
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import java.text.NumberFormat
import java.util.Locale
import java.util.WeakHashMap

/**
 * UI compatibility layer for the programmatic MainActivity.
 *
 * Keeps the existing controls/runtime behavior, while providing:
 * - reachable Start dialog actions;
 * - a persistent multi-coin market selector;
 * - execution-vs-decision counters so SELL decisions are not confused with real closes;
 * - session-synchronized latest execution/event information;
 * - mutually exclusive automatic mode vs manual TP/SL input.
 */
class MireiUiPatchApplication : Application() {
    private val diagnosticsInstalled = WeakHashMap<Activity, Boolean>()
    private val lastMenu = WeakHashMap<View, String>()

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                if (activity is MainActivity) {
                    installStartButtonPatch(activity)
                    installDiagnosticsPatch(activity)
                }
            }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) = Unit
        })
    }

    private fun installStartButtonPatch(activity: Activity) {
        val root = activity.window.decorView
        fun patch() {
            findButtons(root).filter { it.text?.toString() == "MULAI" }.forEach { button ->
                if (button.getTag() == TAG_PATCHED) return@forEach
                button.setTag(TAG_PATCHED)
                button.setOnClickListener { showStartDialog(activity) }
            }
        }
        patch()
        val observer = root.viewTreeObserver
        if (observer.isAlive && root.getTag() != TAG_OBSERVER) {
            root.setTag(TAG_OBSERVER)
            observer.addOnGlobalLayoutListener { patch() }
        }
    }

    private fun installDiagnosticsPatch(activity: MainActivity) {
        val root = activity.window.decorView
        if (diagnosticsInstalled[activity] == true) return
        diagnosticsInstalled[activity] = true
        val observer = root.viewTreeObserver
        if (!observer.isAlive) return
        observer.addOnGlobalLayoutListener {
            val menu = findMenuSpinner(root) ?: return@addOnGlobalLayoutListener
            val selected = menu.selectedItem?.toString().orEmpty()
            if (selected.isBlank()) return@addOnGlobalLayoutListener
            val state = lastMenu[root]
            if (state == selected) return@addOnGlobalLayoutListener
            lastMenu[root] = selected
            when (selected) {
                "PASAR" -> activity.window.decorView.post { renderMarketPulse(activity) }
                "RINGKASAN" -> activity.window.decorView.post { renderSynchronizedSummary(activity) }
                "LOG / AUDIT" -> activity.window.decorView.post { renderReadableAudit(activity) }
            }
        }
    }

    private fun renderMarketPulse(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "PASAR · MARKET PULSE")
        val loading = card(activity, "MEMUAT DATA PASAR…\nMengambil snapshot coin dan menyiapkan market pulse.", 14f)
        content.addView(loading)
        val scanner = parseScanner(intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty())
        val symbols = scanner.map { it.symbol }.distinct().ifEmpty { MireiForegroundService.SUPPORTED_MARKETS }
        val selectedSymbol = arrayOf(symbols.firstOrNull().orEmpty())
        val selectorButton = Button(activity).apply {
            text = "PILIH COIN: ${selectedSymbol[0]}"
            isAllCaps = false
        }
        content.addView(label(activity, "COIN TERPILIH", true))
        content.addView(selectorButton, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT))
        val detail = card(activity, "Pilih coin untuk melihat pulse.", 14f)
        content.addView(detail)
        addTitle(content, "SEMUA COIN · SCANNER")
        scanner.forEach { row -> content.addView(card(activity, "${row.symbol}\nHarga Rp ${row.price}\n1M ${row.change1m}% · Momentum ${row.momentum}% · Trend ${row.trend}% · Porsi volume ${row.volumeShare}%", 13f)) }
        if (scanner.isEmpty()) content.addView(card(activity, "Scanner belum tersedia. Menunggu market data.", 13f))

        fun renderSelected(symbol: String) {
            selectedSymbol[0] = symbol
            selectorButton.text = "PILIH COIN: $symbol"
            detail.text = "MEMUAT $symbol…\nMarket pulse sedang disiapkan."
            Thread {
                val selected = if (symbol == intent.getStringExtra(MireiForegroundService.EXTRA_SYMBOL)) selectedFromCurrentIntent(intent) else null
                val snapshot = selected ?: runCatching { IndodaxMarketDataSource().snapshot(symbol) }.getOrNull()
                val text = if (snapshot != null) {
                    "${snapshot.symbol}\nHarga Rp ${fmtNumber(snapshot.price)}\n" +
                        "1M ${signed(snapshot.change1mPercent)}% · 5M ${signed(snapshot.change5mPercent)}% · 15M ${signed(snapshot.change15mPercent)}%\n" +
                        "Momentum ${signed(snapshot.momentumPercent)}% · Trend ${signed(snapshot.trendScorePercent)}%\n" +
                        "Flow ${signed(snapshot.tradeFlowPercent)}% · Forecast ${(snapshot.forecastConfidence * 100).toInt()}%\n" +
                        "Spread ${fmt(snapshot.spreadPercent)}%\nData ${if (snapshot.dataFresh) "SEGAR" else "STALE"}\nSnapshot: ${formatEpoch(snapshot.snapshotEpochMs)}"
                } else "${symbol}\nData market belum tersedia.\nCoba SEGARKAN DATA atau tunggu runtime selesai setup."
                activity.runOnUiThread {
                    if (!activity.isFinishing) {
                        detail.text = text
                        loading.text = "MARKET READY\nData pulse tersedia untuk ${symbols.size} coin.\nTombol pilihan coin tetap tersedia di atas."
                    }
                }
            }.start()
        }
        selectorButton.setOnClickListener {
            val checked = symbols.indexOf(selectedSymbol[0]).coerceAtLeast(0)
            AlertDialog.Builder(activity)
                .setTitle("PILIH COIN · MARKET PULSE")
                .setSingleChoiceItems(symbols.toTypedArray(), checked) { dialog, which ->
                    symbols.getOrNull(which)?.let(::renderSelected)
                    dialog.dismiss()
                }
                .setNegativeButton("BATAL", null)
                .show()
        }
        symbols.firstOrNull()?.let(::renderSelected)
    }

    private fun renderSynchronizedSummary(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "RINGKASAN · SESI SINKRON")
        val start = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(200).filter { start == 0L || it.openedAtEpochMs >= start } }.getOrDefault(emptyList())
        val closes = trades.filter { it.closedAtEpochMs != null }
        val opens = trades.filter { start == 0L || it.openedAtEpochMs >= start }
        val reEntries = runCatching { db.recentAudit(300).count { it.createdAtEpochMs >= start && it.eventType == "RE_ENTRY" } }.getOrDefault(0)
        val lastClose = closes.maxByOrNull { it.closedAtEpochMs ?: 0L }
        val lastOpen = trades.maxByOrNull { it.openedAtEpochMs }
        val sellDecisions = intent.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)
        val holdDecisions = intent.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)
        val buyDecisions = intent.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)
        content.addView(card(activity,
            "STATUS\n${intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP"}\n\n" +
                "KEPUTUSAN ENGINE\nBUY $buyDecisions · HOLD $holdDecisions · SELL $sellDecisions\n" +
                "Catatan: SELL di atas adalah keputusan engine, BUKAN jumlah posisi yang terjual.\n\n" +
                "EKSEKUSI NYATA\nOPEN ${opens.size} · CLOSE ${closes.size} · RE-ENTRY $reEntries", 14f))
        addTitle(content, "EVENT TERAKHIR · SUMBER DATABASE")
        if (lastClose != null) content.addView(card(activity,
            "CLOSE TERAKHIR\n${formatEpoch(lastClose.closedAtEpochMs ?: 0L)} · ${lastClose.symbol}\n" +
                "Masuk Rp ${fmtNumber(lastClose.entryPrice ?: 0.0)}\nKeluar Rp ${fmtNumber(lastClose.exitPrice ?: 0.0)}\n" +
                "PnL Rp ${signedMoney(lastClose.pnlIdr)}\nAlasan: ${humanExitReason(lastClose.exitReason)}", 13.5f))
        else content.addView(card(activity, "Belum ada CLOSE nyata pada sesi ini.", 13.5f))
        if (lastOpen != null) content.addView(card(activity,
            "OPEN TERAKHIR\n${formatEpoch(lastOpen.openedAtEpochMs)} · ${lastOpen.symbol}\n" +
                "Entry Rp ${fmtNumber(lastOpen.entryPrice ?: 0.0)}\nModal Rp ${fmtNumber(lastOpen.stakeIdr)}\nAsal: ${lastOpen.entryReason}", 13.5f))
        addTitle(content, "RE-ENTRY / BUY OTOMATIS")
        val gate = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty().ifBlank { "Belum ada gate terakhir." }
        val reentryText = if (lastClose == null) {
            "Belum ada posisi yang ditutup. Belum ada recovery yang dapat diuji."
        } else if (reEntries > 0) {
            "RE-ENTRY terdeteksi ${reEntries}x. Ini membuktikan modal hasil CLOSE dapat kembali masuk saat gate BUY valid atau setelah TP."
        } else {
            "Belum ada RE-ENTRY pada sesi ini.\nGate terakhir: ${gate.replace("|", "\n")}"
        }
        content.addView(card(activity, reentryText, 13.5f))
        addTitle(content, "HITUNGAN KEPUTUSAN")
        content.addView(card(activity,
            "BUY / MASUK (KEPUTUSAN): $buyDecisions\nHOLD / TAHAN (KEPUTUSAN): $holdDecisions\nSELL / KELUAR (KEPUTUSAN): $sellDecisions\n\n" +
                "CLOSE NYATA: ${closes.size}\nOPEN NYATA: ${opens.size}\n\nSELL $sellDecisions tidak berarti $sellDecisions coin dijual. Hanya event CLOSE nyata yang mengubah posisi dan tercatat sebagai transaksi.", 14f))
    }

    private fun renderReadableAudit(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "LOG / AUDIT · SESI INI")
        val start = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(200).filter { start == 0L || it.openedAtEpochMs >= start } }.getOrDefault(emptyList())
        val closes = trades.filter { it.closedAtEpochMs != null }.sortedByDescending { it.closedAtEpochMs ?: 0L }
        val opens = trades.sortedByDescending { it.openedAtEpochMs }
        content.addView(card(activity,
            "AUDIT DIBACA DARI DATABASE SESI AKTIF.\nOPEN nyata: ${opens.size}\nCLOSE nyata: ${closes.size}\nSELL decision count tidak dihitung sebagai penjualan di halaman ini.", 13.5f))
        addTitle(content, "EKSEKUSI NYATA")
        val executionTrades = (opens + closes).distinctBy { "${it.symbol}|${it.openedAtEpochMs}|${it.closedAtEpochMs}|${it.exitPrice}" }
        if (executionTrades.isEmpty()) content.addView(card(activity, "Belum ada transaksi nyata pada sesi ini.", 13f))
        else executionTrades.sortedByDescending { maxOf(it.openedAtEpochMs, it.closedAtEpochMs ?: 0L) }.take(100).forEach { trade ->
            val status = if (trade.closedAtEpochMs == null) "OPEN AKTIF" else "CLOSE NYATA"
            content.addView(card(activity,
                "${formatEpoch(trade.closedAtEpochMs ?: trade.openedAtEpochMs)} · $status · ${trade.symbol}\n" +
                    "Modal Rp ${fmtNumber(trade.stakeIdr)}\nEntry Rp ${fmtNumber(trade.entryPrice ?: 0.0)}\n" +
                    "Keluar ${trade.exitPrice?.let { "Rp ${fmtNumber(it)}" } ?: "—"}\nPnL Rp ${signedMoney(trade.pnlIdr)}\n" +
                    "Alasan masuk: ${trade.entryReason}\nAlasan keluar: ${humanExitReason(trade.exitReason)}", 12.5f))
        }
        addTitle(content, "EVENT ENGINE")
        val events = runCatching {
            db.recentAudit(200).filter { start == 0L || it.createdAtEpochMs >= start }
                .filter { it.eventType in setOf("OPEN", "RE_ENTRY", "SL_CLOSE", "TP_CLOSE", "MANUAL_CLOSE", "SESSION_STOPPED", "SESSION_PAUSED", "SESSION_CLOSED", "RUNTIME_ERROR") }
                .sortedByDescending { it.createdAtEpochMs }
        }.getOrDefault(emptyList())
        events.take(100).forEach { event -> content.addView(card(activity, "${formatEpoch(event.createdAtEpochMs)} · ${humanEventType(event.eventType)}\n${humanAuditDetails(event.details)}", 12.5f)) }
        if (events.isEmpty()) content.addView(card(activity, "Belum ada event engine pada sesi ini.", 12.5f))
    }

    private fun contentOf(activity: MainActivity): LinearLayout? = runCatching { MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(activity) as LinearLayout }.getOrNull()
    private fun currentIntentOf(activity: MainActivity): Intent? = runCatching { MainActivity::class.java.getDeclaredField("currentIntent").apply { isAccessible = true }.get(activity) as? Intent }.getOrNull()

    private fun findMenuSpinner(view: View): Spinner? {
        if (view is Spinner) {
            val selected = view.selectedItem?.toString().orEmpty()
            if (selected in setOf("RINGKASAN", "PASAR", "POSISI", "AKTIVITAS", "KEPUTUSAN", "RISIKO", "EXCHANGE / API", "PENGATURAN", "LOG / AUDIT")) return view
        }
        if (view !is ViewGroup) return null
        for (i in 0 until view.childCount) findMenuSpinner(view.getChildAt(i))?.let { return it }
        return null
    }

    private data class ScannerRow(val symbol: String, val price: String, val change1m: String, val momentum: String, val trend: String, val volumeShare: String)
    private fun parseScanner(raw: String): List<ScannerRow> = raw.lines().mapNotNull { line -> val p = line.split('|'); if (p.size >= 6) ScannerRow(p[0], p[1], p[2], p[3], p[4], p[5]) else null }

    private fun selectedFromCurrentIntent(intent: Intent) = com.mirei.app.core.MarketSnapshot(
        symbol = intent.getStringExtra(MireiForegroundService.EXTRA_SYMBOL) ?: "", price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0),
        momentumPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_MOMENTUM, 0.0), volatilityPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_VOLATILITY, 0.0),
        sentimentScore = intent.getDoubleExtra(MireiForegroundService.EXTRA_SENTIMENT, 0.0), forecastConfidence = intent.getDoubleExtra(MireiForegroundService.EXTRA_FORECAST_CONFIDENCE, 0.0),
        dataFresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false), bidPrice = intent.getDoubleExtra(MireiForegroundService.EXTRA_BID, 0.0), askPrice = intent.getDoubleExtra(MireiForegroundService.EXTRA_ASK, 0.0),
        high24h = intent.getDoubleExtra(MireiForegroundService.EXTRA_HIGH_24H, 0.0), low24h = intent.getDoubleExtra(MireiForegroundService.EXTRA_LOW_24H, 0.0), volume24h = intent.getDoubleExtra(MireiForegroundService.EXTRA_VOLUME_24H, 0.0),
        spreadPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_SPREAD, 0.0), changeSinceLastTickPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_TICK, 0.0),
        change1mPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_1M, 0.0), change5mPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_5M, 0.0), change15mPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_CHANGE_15M, 0.0),
        tradeFlowPercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_FLOW, 0.0), tradeCount = intent.getIntExtra(MireiForegroundService.EXTRA_TRADE_COUNT, 0), buyVolume = intent.getDoubleExtra(MireiForegroundService.EXTRA_BUY_VOLUME, 0.0),
        sellVolume = intent.getDoubleExtra(MireiForegroundService.EXTRA_SELL_VOLUME, 0.0), lastTradeEpochMs = intent.getLongExtra(MireiForegroundService.EXTRA_LAST_TRADE, 0L), snapshotEpochMs = intent.getLongExtra(MireiForegroundService.EXTRA_SNAPSHOT_TIME, 0L),
        sourceAgeMs = intent.getLongExtra(MireiForegroundService.EXTRA_SOURCE_AGE, 0L), trendScorePercent = intent.getDoubleExtra(MireiForegroundService.EXTRA_TREND, 0.0),
    )

    private fun humanAuditDetails(details: String): String {
        val parts = details.split('|'); val reason = parts.firstOrNull().orEmpty().replace('_', ' '); val order = parts.getOrNull(1)?.takeIf { it != "-" }
        val pnl = parts.firstOrNull { it.startsWith("pnl=") }?.removePrefix("pnl="); val before = parts.firstOrNull { it.startsWith("balance_before=") }?.removePrefix("balance_before="); val after = parts.firstOrNull { it.startsWith("balance_after=") }?.removePrefix("balance_after=")
        return buildString { append("Aksi: ").append(reason.ifBlank { "event" }).append('\n'); if (order != null) append("Order: ").append(order).append('\n'); if (pnl != null) append("PnL: Rp ").append(pnl).append('\n'); if (before != null) append("Kas sebelum: Rp ").append(before).append('\n'); if (after != null) append("Kas sesudah: Rp ").append(after) }.trim()
    }
    private fun humanEventType(type: String): String = when (type) {
        "OPEN" -> "OPEN · POSISI MASUK"; "RE_ENTRY" -> "RE-ENTRY · BUY KEMBALI"; "SL_CLOSE" -> "CLOSE · STOP LOSS"; "TP_CLOSE" -> "CLOSE · TAKE PROFIT"; "MANUAL_CLOSE" -> "CLOSE · MANUAL"; "SESSION_STOPPED" -> "SESI · BERHENTI"; "SESSION_PAUSED" -> "SESI · HOLD"; "SESSION_CLOSED" -> "SESI · SEMUA POSISI DITUTUP"; "RUNTIME_ERROR" -> "ERROR RUNTIME"; else -> type.replace('_', ' ')
    }
    private fun humanExitReason(reason: String?): String = when (reason) { "stop_loss" -> "STOP LOSS"; "take_profit" -> "TAKE PROFIT"; "ai_close" -> "KEPUTUSAN AI CLOSE"; "manual_close_all" -> "TUTUP SEMUA POSISI"; else -> reason?.replace('_', ' ') ?: "—" }
    private fun addTitle(content: LinearLayout, value: String) { content.addView(label(content.context, value, true)) }
    private fun card(context: Context, value: String, size: Float): TextView = TextView(context).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(8, 10, 8, 10); setBackgroundColor(Color.rgb(24, 34, 43)) }
    private fun label(context: Context, value: String, bold: Boolean): TextView = TextView(context).apply { text = value; textSize = if (bold) 17f else 14f; setTextColor(Color.WHITE); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(4, 10, 4, 5) }
    private fun fmtNumber(value: Double): String = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)
    private fun fmt(value: Double): String = "%.3f".format(Locale.US, value)
    private fun signed(value: Double): String = if (value >= 0) "+%.3f".format(Locale.US, value) else "%.3f".format(Locale.US, value)
    private fun signedMoney(value: Double): String = if (value >= 0) "+${fmtNumber(value)}" else "-${fmtNumber(kotlin.math.abs(value))}"
    private fun formatEpoch(epochMs: Long): String = if (epochMs <= 0L) "—" else java.text.SimpleDateFormat("MM/dd/HH/mm/ss", Locale.US).format(java.util.Date(epochMs))

    private fun showStartDialog(activity: Activity) {
        val prefs = activity.getSharedPreferences("mirei_settings", Context.MODE_PRIVATE)
        val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
        val scroll = ScrollView(activity).apply { isFillViewport = false; clipToPadding = true; setPadding(0, 0, 0, 4) }
        val outer = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 4, 16, 14) }; scroll.addView(outer, ViewGroup.LayoutParams(-1, -2))
        outer.addView(label(activity, "Konfigurasi sesi sebelum runtime dimulai.", false)); outer.addView(label(activity, "1. COIN & MODAL", true)); outer.addView(label(activity, "Pilih 1–3 coin. Modal pada baris coin menjadi modal beli pertama dan dapat menjadi acuan TP/SL.", false))
        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val rows = MireiForegroundService.SUPPORTED_MARKETS.mapIndexed { index, market ->
            val check = CheckBox(activity).apply { text = market; textSize = 15f; isChecked = index < 3 }
            val amount = EditText(activity).apply { hint = "Modal IDR"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(if (index < 3) "50000" else ""); isEnabled = check.isChecked; setPadding(8, 4, 8, 4) }
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL; setPadding(4, 4, 4, 4) }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)); row.addView(amount, LinearLayout.LayoutParams(132, ViewGroup.LayoutParams.WRAP_CONTENT)); list.addView(row); market to Pair(check, amount)
        }
        outer.addView(list, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT)); outer.addView(label(activity, "2. MODE TRADING", true))
        val modeSpinner = Spinner(activity); val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY"); modeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, modes); modeSpinner.setSelection(modes.indexOf(prefs.getString("mode", "BALANCED")).coerceAtLeast(0)); outer.addView(modeSpinner, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT))
        outer.addView(label(activity, "3. DASAR PEMANTAUAN TP / SL", true)); val basisGroup = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL }
        val entryRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "Harga ENTRY COIN — pendekatan harga entry tetap tersedia"; textSize = 15f }; val capitalRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "MODAL SIKLUS — target/rugi IDR mengikuti modal beli pertama dan bertambah setelah TP"; textSize = 15f }
        basisGroup.addView(entryRadio); basisGroup.addView(capitalRadio); val savedBasis = prefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name); basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id); outer.addView(basisGroup)
        outer.addView(card(activity, "Dengan dasar MODAL SIKLUS, modal Rp50.000 dan TP 1% menghasilkan target Rp500. Setelah TP tercapai, siklus berikutnya menggunakan sekitar Rp50.500 sebelum fee/slippage aktual simulator.", 13f)); outer.addView(label(activity, "4. TP / SL", true))
        val manualSwitch = Switch(activity).apply { text = "TP / SL MANUAL"; textSize = 15f; isChecked = prefs.getBoolean("manual_risk", false) }; outer.addView(manualSwitch)
        val fields = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }; val slField = EditText(activity).apply { hint = "SL %"; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(prefs.getString("manual_sl", "0.00")); setPadding(8, 4, 8, 4) }; val tpField = EditText(activity).apply { hint = "TP %"; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(prefs.getString("manual_tp", "1.00")); setPadding(8, 4, 8, 4) }
        fields.addView(slField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 10 }); fields.addView(tpField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)); fields.visibility = if (manualSwitch.isChecked) View.VISIBLE else View.GONE; manualSwitch.setOnCheckedChangeListener { _, checked -> fields.visibility = if (checked) View.VISIBLE else View.GONE; modeSpinner.isEnabled = !checked }; modeSpinner.isEnabled = !manualSwitch.isChecked; outer.addView(fields)
        outer.addView(card(activity, "MODE OTOMATIS: AGGRESSIVE memakai SL 0% (unlimited hold) dan TP 1%; BALANCED/SAFETY memakai template masing-masing. MODE MANUAL: angka TP/SL di bawah menjadi satu-satunya sumber TP/SL dan pilihan mode otomatis dinonaktifkan.", 13f))
        val dialog = AlertDialog.Builder(activity).setTitle("MULAI SESI PAPER").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.window?.apply { setLayout((activity.resources.displayMetrics.widthPixels * 0.94f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.90f).toInt()); setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE) }
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).minHeight = 52; dialog.getButton(AlertDialog.BUTTON_POSITIVE).minHeight = 52
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val selected = rows.mapNotNull { (market, pair) -> val (check, amount) = pair; if (!check.isChecked) null else amount.text.toString().toDoubleOrNull()?.takeIf { it > 0.0 }?.let { market to it } }
                if (selected.isEmpty() || selected.size > 3) { dialog.setTitle("MULAI SESI PAPER · PERIKSA INPUT"); dialog.setMessage("Pilih minimal 1 dan maksimal 3 coin, dengan modal > 0."); return@setOnClickListener }
                val total = selected.sumOf { it.second }; if (total > 150_000.0 + 1e-6) { dialog.setTitle("MULAI SESI PAPER · PERIKSA INPUT"); dialog.setMessage("Total modal Rp ${numberFormat.format(total)} melebihi Rp150.000."); return@setOnClickListener }
                val manual = manualSwitch.isChecked; val sl = slField.text.toString().toDoubleOrNull(); val tp = tpField.text.toString().toDoubleOrNull(); if (manual && (sl == null || tp == null || sl < 0.0 || tp <= sl)) { dialog.setTitle("MULAI SESI PAPER · PERIKSA INPUT"); dialog.setMessage("TP manual harus lebih besar dari SL manual. SL 0% berarti unlimited hold sampai TP."); return@setOnClickListener }
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                prefs.edit().putString("mode", modeSpinner.selectedItem.toString()).putBoolean("manual_risk", manual).putString("manual_sl", (sl ?: 0.00).toString()).putString("manual_tp", (tp ?: 1.00).toString()).putString("risk_basis", basisMode.name).apply()
                val allocations = selected.joinToString(";") { "${it.first}=${it.second}" }; sendService(activity, MireiForegroundService.ACTION_APPLY_RISK)
                activity.window.decorView.postDelayed({ sendService(activity, MireiForegroundService.ACTION_START) { putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations); putExtra(MireiForegroundService.EXTRA_SYMBOL, selected.first().first); putExtra(MireiForegroundService.EXTRA_EXCHANGE, "indodax") } }, 180L); dialog.dismiss()
            }
        }; dialog.show()
    }

    private fun sendService(activity: Activity, action: String, extras: Intent.() -> Unit = {}) { val intent = Intent(activity, MireiForegroundService::class.java).apply { this.action = action; extras() }; runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) } }

    private fun findButtons(view: View): List<Button> { if (view is Button) return listOf(view); if (view !is ViewGroup) return emptyList(); return buildList { for (index in 0 until view.childCount) addAll(findButtons(view.getChildAt(index))) } }
    companion object { private val TAG_PATCHED = Any(); private val TAG_OBSERVER = Any() }
}
