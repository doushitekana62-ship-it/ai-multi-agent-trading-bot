package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.app.Application
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
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
import android.widget.TableLayout
import android.widget.TableRow
import android.widget.TextView
import android.widget.Toast
import com.mirei.app.core.AssetClass
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.TradingGlossary
import com.mirei.app.core.TradingUniverse
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.storage.TradeRow
import java.text.NumberFormat
import java.util.Locale
import java.util.WeakHashMap

/**
 * UI compatibility layer for the programmatic MainActivity.
 * Runtime ownership remains in MainActivity/ForegroundService. This class only
 * changes presentation and exposes additional paper-only controls without
 * replacing the whole Activity or touching the trading engine.
 */
class MireiUiPatchApplication : Application() {
    private val diagnosticsInstalled = WeakHashMap<Activity, Boolean>()
    private val lastMenu = WeakHashMap<View, String>()
    private val lastTick = WeakHashMap<View, Long>()

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
            val intent = currentIntentOf(activity)
            val tick = intent?.getLongExtra(MireiForegroundService.EXTRA_TICK, 0L) ?: 0L
            val menuChanged = lastMenu[root] != selected
            val tickChanged = lastTick[root] != tick
            if (!menuChanged && !tickChanged) return@addOnGlobalLayoutListener
            lastMenu[root] = selected
            lastTick[root] = tick
            activity.window.decorView.post {
                when (selected) {
                    "PASAR" -> renderMarketPulse(activity)
                    "RINGKASAN" -> renderDashboard(activity)
                    "POSISI" -> renderPositionsTable(activity)
                    "LOG / AUDIT" -> renderReadableAudit(activity)
                    else -> renderStatusLegend(activity)
                }
            }
        }
    }

    private fun renderStatusLegend(activity: Activity) {
        val intent = currentIntentOf(activity) ?: return
        val status = statusIndicator(intent)
        val title = currentContent(activity)?.let { it.findViewWithTag<TextView>(STATUS_TAG) } ?: return
        title.text = status
    }

    private fun renderMarketPulse(activity: Activity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "PASAR · MARKET PULSE TABLE")
        val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        val online = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
        content.addView(card(activity,
            if (fresh && online) "🟢 DATA MARKET SEGAR · SOURCE: INDODAX API\nTidak menggunakan grafik. Tabel diperbarui mengikuti scanner runtime." else "🔵 LOADING / SEARCHING CONNECTION…\nMenunggu snapshot market terbaru.", 13.5f))

        val scanner = parseScanner(intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty())
        if (scanner.isEmpty()) {
            content.addView(card(activity, "Market pulse belum tersedia. Tekan SEGARKAN DATA atau lanjutkan sesi.", 13f))
            return
        }
        addTitle(content, "SCANNER · SEMUA COIN TERPANTAU")
        val table = TableLayout(activity).apply { isStretchAllColumns = false; setPadding(2, 4, 2, 12) }
        table.addView(tableRow(activity, listOf("COIN", "HARGA", "1M", "5M", "15M", "MOM", "TREND", "FLOW"), true))
        scanner.forEach { row ->
            val tr = TableRow(activity)
            val values = listOf(row.symbol, row.price, signedText(row.change1m), "—", "—", signedText(row.momentum), signedText(row.trend), "—")
            values.forEachIndexed { index, value ->
                val tv = cell(activity, value)
                when (index) {
                    0 -> tv.setTextColor(directionColor(parse(row.trend)))
                    1 -> tv.setTextColor(directionColor(parse(row.change1m)))
                    2, 5, 6 -> tv.setTextColor(directionColor(parse(value)))
                }
                tr.addView(tv)
            }
            table.addView(tr)
        }
        content.addView(table)
        addTitle(content, "SUGESTI MIREI · BERDASARKAN API EXCHANGE AKTIF")
        val ranked = scanner.sortedByDescending { parse(it.trend) * 0.5 + parse(it.momentum) * 0.3 + parse(it.change1m) * 0.2 }.take(3)
        ranked.forEachIndexed { index, row ->
            content.addView(card(activity, "${index + 1}. ${row.symbol}\nTrend ${signedText(row.trend)}% · Momentum ${signedText(row.momentum)}% · 1M ${signedText(row.change1m)}%\nSumber: scanner Indodax dalam sesi paper. Ini sugesti, bukan jaminan profit.", 12.8f))
        }
        addTitle(content, "STATUS WARNA")
        content.addView(card(activity, "🟢 naik / positif   🔴 turun / negatif   ⚪ flat / mendekati nol\nWarna diterapkan pada nama coin atau nilai, bukan seluruh tabel.", 12.5f))
    }

    private fun renderDashboard(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "RINGKASAN · DASHBOARD")
        content.addView(card(activity, statusIndicator(intent), 15f))
        val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE).orEmpty()
        val start = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(300).filter { start == 0L || it.openedAtEpochMs >= start } }.getOrDefault(emptyList())
        val closed = trades.filter { it.closedAtEpochMs != null }
        val wins = closed.count { it.pnlIdr > 0.0 }
        val winRate = if (closed.isEmpty()) 0.0 else wins * 100.0 / closed.size
        val suggestions = runCatching { db.recentSuggestions(500).filter { start == 0L || it.createdAtEpochMs >= start } }.getOrDefault(emptyList())
        val aiBuy = suggestions.count { it.action == "BUY" }
        val aiHold = suggestions.count { it.action == "HOLD" }
        val aiSell = suggestions.count { it.action == "CLOSE" || it.action == "SELL" }
        val actualBuy = trades.count { it.status == "OPEN" }
        val actualSell = closed.size

        content.addView(card(activity,
            "EQUITY     Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n" +
                "KAS        Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n" +
                "POSISI     ${intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}/3\n" +
                "WIN RATE   ${"%.2f".format(Locale.US, winRate)}% (${wins}/${closed.size} close menang)\n" +
                "SESSION    ${if (state == "RUNNING") "AKTIF" else state.ifBlank { "STOP" }}", 14f))

        addTitle(content, "AI VS ACTUAL · SESI INI")
        val compare = TableLayout(activity).apply { isStretchAllColumns = true }
        compare.addView(tableRow(activity, listOf("SUMBER", "BUY", "HOLD", "SELL"), true))
        compare.addView(tableRow(activity, listOf("AI DECISION", aiBuy.toString(), aiHold.toString(), aiSell.toString()), false))
        compare.addView(tableRow(activity, listOf("ACTUAL PAPER", actualBuy.toString(), "0", actualSell.toString()), false))
        content.addView(compare)
        content.addView(card(activity, "ACTUAL PAPER memakai ledger OPEN/CLOSE. HOLD actual = 0 karena HOLD adalah keputusan, bukan order book execution. SELL AI tidak dihitung sebagai close nyata.", 12.2f))

        addTitle(content, "KONTROL SESI")
        val controls = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; setPadding(0, 6, 0, 10) }
        controls.addView(actionButton(activity, "LANJUTKAN", enabled = state != "RUNNING") { sendService(activity, MireiForegroundService.ACTION_START) })
        controls.addView(actionButton(activity, "TOP UP", enabled = true) { showTopUpDialog(activity) })
        content.addView(controls)

        val tools = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; setPadding(0, 2, 0, 8) }
        tools.addView(actionButton(activity, "KALKULATOR", true) { showCalculator(activity) })
        tools.addView(actionButton(activity, "KAMUS", true) { showGlossary(activity) })
        tools.addView(actionButton(activity, "JENIS TRADING", true) { showTradingUniverse(activity) })
        content.addView(tools)

        addTitle(content, "3 POSISI")
        renderPositionRowsInto(content, intent, showHeader = true)
        addTitle(content, "SISTEM & LOADING")
        content.addView(card(activity, "🟢 running · 🔴 damage · 🟡 stopped/hold · 🔵 searching connection · ⚪ close all\nMarket/API functions display loading when snapshot is not fresh. Resume does not recreate the session; it restores persisted cash, positions, counters and market selection.", 12.5f))

        addTitle(content, "MULTI-ASSET CONNECTOR CATALOG")
        content.addView(card(activity, "Crypto: Indodax/Bybit/OKX catalog. Saham: Alpaca API. Forex & metals/CFD: OANDA API. Non-crypto adapters are catalogued for connection work; the current live paper runtime remains Indodax-only until the adapter is enabled. This preserves the working Build 194 execution path.", 12.5f))
    }

    private fun renderPositionsTable(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "POSISI · 3 SLOT REAL-TIME")
        val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        content.addView(card(activity, if (fresh) "🟢 UPDATE MARKET TERBARU" else "🔵 LOADING / MENUNGGU MARKET TERBARU", 13f))
        renderPositionRowsInto(content, intent, showHeader = true)
    }

    private fun renderPositionRowsInto(content: LinearLayout, intent: Intent, showHeader: Boolean) {
        val rows = parsePositions(intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        val table = TableLayout(content.context).apply { isStretchAllColumns = false; setPadding(0, 4, 0, 8) }
        if (showHeader) table.addView(tableRow(content.context, listOf("#", "COIN", "MODAL", "ENTRY", "NOW", "TP", "SL", "UNREALIZED", "UMUR"), true))
        for (slot in 0 until 3) {
            val p = rows.getOrNull(slot)
            if (p == null) {
                table.addView(tableRow(content.context, listOf("${slot + 1}", "EMPTY", "—", "—", "—", "—", "—", "—", "—"), false))
            } else {
                val now = p["current"]?.toDoubleOrNull() ?: 0.0
                val entry = p["entry"]?.toDoubleOrNull() ?: 0.0
                val stake = p["stake"]?.toDoubleOrNull() ?: 0.0
                val tp = p["tp"]?.toDoubleOrNull() ?: 0.0
                val sl = p["sl"]?.toDoubleOrNull() ?: 0.0
                val cap = p["risk_capital"]?.toDoubleOrNull()?.takeIf { it > 0 } ?: stake
                val qty = if (entry > 0) stake / entry else 0.0
                val tpEntryPct = p["tp_pct"]?.toDoubleOrNull() ?: 0.0
                val slEntryPct = p["sl_pct"]?.toDoubleOrNull() ?: 0.0
                val tpCapPct = if (qty > 0 && cap > 0) ((tp - entry) * qty / cap) * 100.0 else 0.0
                val slCapPct = if (sl == 0.0 || qty <= 0.0 || cap <= 0.0) 0.0 else ((sl - entry) * qty / cap) * 100.0
                val age = ageText(p["opened"]?.toLongOrNull() ?: 0L)
                val base = listOf(
                    "${slot + 1}", p["symbol"].orEmpty(), money(stake), money(entry), money(now),
                    "${money(tp)} (${signedText(tpEntryPct)}% entry / +${"%.3f".format(Locale.US, tpCapPct)}% modal)",
                    if (sl == 0.0) "UNLIMITED" else "${money(sl)} (${signedText(slEntryPct)}% entry / ${"%.3f".format(Locale.US, slCapPct)}% modal)",
                    signedMoney(p["unrealized"]?.toDoubleOrNull() ?: 0.0), age,
                )
                val row = TableRow(content.context)
                base.forEachIndexed { index, value ->
                    val tv = cell(content.context, value)
                    if (index == 1) tv.setTextColor(directionColor(if (now >= entry) 1.0 else -1.0))
                    if (index == 7) tv.setTextColor(directionColor(p["unrealized"]?.toDoubleOrNull() ?: 0.0))
                    row.addView(tv)
                }
                table.addView(row)
            }
        }
        content.addView(table)
        content.addView(card(content.context, "TP/SL entry = pergerakan harga dari entry. TP/SL modal = perhitungan real terhadap modal acuan yang tersimpan pada posisi, bukan hardcode.", 12.2f))
    }

    private fun renderReadableAudit(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        val intent = currentIntentOf(activity) ?: return
        content.removeAllViews()
        addTitle(content, "LOG / AUDIT · TABLE SESI INI")
        val start = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(300).filter { start == 0L || it.openedAtEpochMs >= start } }.getOrDefault(emptyList())
        val closes = trades.count { it.closedAtEpochMs != null }
        val wins = trades.count { it.closedAtEpochMs != null && it.pnlIdr > 0.0 }
        val buy = intent.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)
        val hold = intent.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)
        val sell = intent.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)
        content.addView(card(activity, "OPEN nyata ${trades.size} · CLOSE nyata $closes · WIN RATE ${if (closes == 0) "0.00" else "%.2f".format(Locale.US, wins * 100.0 / closes)}%\nAI BUY $buy · HOLD $hold · SELL $sell", 13f))

        val table = TableLayout(activity).apply { isStretchAllColumns = false; setPadding(0, 6, 0, 8) }
        table.addView(tableRow(activity, listOf("WAKTU", "EVENT", "COIN", "STATUS", "PNL", "DETAIL"), true))
        trades.sortedByDescending { maxOf(it.openedAtEpochMs, it.closedAtEpochMs ?: 0L) }.take(120).forEach { trade ->
            val status = if (trade.closedAtEpochMs == null) "OPEN" else "CLOSE"
            val event = if (trade.closedAtEpochMs == null) trade.entryReason else humanExitReason(trade.exitReason)
            table.addView(tableRow(activity, listOf(formatEpoch(trade.closedAtEpochMs ?: trade.openedAtEpochMs), event, trade.symbol, status, signedMoney(trade.pnlIdr), "Entry ${money(trade.entryPrice ?: 0.0)} → ${trade.exitPrice?.let { money(it) } ?: "—"}"), false))
        }
        runCatching { db.recentAudit(150).filter { start == 0L || it.createdAtEpochMs >= start } }.getOrDefault(emptyList()).forEach { event ->
            table.addView(tableRow(activity, listOf(formatEpoch(event.createdAtEpochMs), humanEventType(event.eventType), "—", "ENGINE", "—", humanAuditDetails(event.details)), false))
        }
        content.addView(table)
        content.addView(card(activity, "Audit memakai satu tabel kronologis. SELL decision tidak dihitung sebagai CLOSE kecuali ada trade ledger record nyata.", 12.2f))
    }

    private fun showStartDialog(activity: Activity) {
        val prefs = activity.getSharedPreferences("mirei_settings", Context.MODE_PRIVATE)
        val format = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
        val savedCapital = prefs.getString("total_capital", null)?.toDoubleOrNull()?.takeIf { it > 0 } ?: 150_000.0
        val scroll = ScrollView(activity).apply { isFillViewport = true; setPadding(10, 8, 10, 18) }
        val outer = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 14, 18, 24) }
        scroll.addView(outer, ViewGroup.LayoutParams(-1, -2))
        outer.addView(label(activity, "Konfigurasi sesi. Build 194 runtime tetap dipertahankan; angka modal sekarang editable.", false))
        outer.addView(label(activity, "1. TOTAL MODAL / DANA PAPER", true))
        val capitalField = moneyField(activity, savedCapital)
        outer.addView(capitalField, spacedParams())
        outer.addView(card(activity, "Masukan total dana yang boleh dipakai sesi. Tidak ada lagi batas hardcode Rp150.000.", 12.5f), spacedParams())

        outer.addView(label(activity, "2. COIN & MODAL PER POSISI", true), spacedParams())
        outer.addView(label(activity, "Pilih 1–3 coin. Total modal per coin harus ≤ total modal sesi.", false), spacedParams())
        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(2, 4, 2, 10) }
        val defaultEach = savedCapital / 3.0
        val rows = MireiForegroundService.SUPPORTED_MARKETS.mapIndexed { index, market ->
            val check = CheckBox(activity).apply { text = market; textSize = 15f; isChecked = index < 3 }
            val amount = EditText(activity).apply { hint = "Modal IDR"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(if (index < 3) format.format(defaultEach) else ""); isEnabled = check.isChecked; setPadding(12, 8, 12, 8); minimumHeight = 48 }
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(8, 7, 8, 7) }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(amount, LinearLayout.LayoutParams(150, ViewGroup.LayoutParams.WRAP_CONTENT))
            list.addView(row, spacedParams(8))
            market to Pair(check, amount)
        }
        outer.addView(list)

        outer.addView(label(activity, "3. MODE TRADING", true), spacedParams())
        val modeSpinner = Spinner(activity)
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        modeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, modes)
        modeSpinner.setSelection(modes.indexOf(prefs.getString("mode", "BALANCED")).coerceAtLeast(0))
        outer.addView(modeSpinner, spacedParams())

        outer.addView(label(activity, "4. DASAR TP / SL", true), spacedParams())
        val basisGroup = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL; setPadding(8, 4, 8, 4) }
        val entryRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "ENTRY PRICE — target berbasis harga entry"; textSize = 15f; setPadding(0, 6, 0, 6) }
        val capitalRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "INITIAL CAPITAL — target IDR berbasis modal acuan"; textSize = 15f; setPadding(0, 6, 0, 6) }
        basisGroup.addView(entryRadio); basisGroup.addView(capitalRadio)
        basisGroup.check(if (prefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name) == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        outer.addView(basisGroup, spacedParams())

        outer.addView(label(activity, "5. TP / SL MANUAL", true), spacedParams())
        val manualSwitch = Switch(activity).apply { text = "TP / SL MANUAL"; textSize = 15f; isChecked = prefs.getBoolean("manual_risk", false); setPadding(8, 6, 8, 6) }
        outer.addView(manualSwitch, spacedParams())
        val fields = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; setPadding(4, 4, 4, 4) }
        val slField = percentField(activity, prefs.getString("manual_sl", "0.00")?.toDoubleOrNull() ?: 0.0, "SL %")
        val tpField = percentField(activity, prefs.getString("manual_tp", "1.00")?.toDoubleOrNull() ?: 1.0, "TP %")
        fields.addView(slField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 12 })
        fields.addView(tpField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        fields.visibility = if (manualSwitch.isChecked) View.VISIBLE else View.GONE
        manualSwitch.setOnCheckedChangeListener { _, checked -> fields.visibility = if (checked) View.VISIBLE else View.GONE; modeSpinner.isEnabled = !checked }
        modeSpinner.isEnabled = !manualSwitch.isChecked
        outer.addView(fields, spacedParams())
        outer.addView(card(activity, "SL 0% = unlimited hold sampai TP atau tutup manual. Angka pada mode INITIAL CAPITAL dihitung dari modal input tersimpan, bukan tulisan tetap.", 12.5f), spacedParams())

        val dialog = AlertDialog.Builder(activity).setTitle("MULAI SESI PAPER").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.window?.apply {
                setLayout((activity.resources.displayMetrics.widthPixels * 0.94f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.92f).toInt())
                setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
            }
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).minHeight = 54
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).minHeight = 54
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val totalCapital = capitalField.text.toString().replace(".", "").replace(",", ".").toDoubleOrNull() ?: 0.0
                val selected = rows.mapNotNull { (market, pair) ->
                    val (check, amount) = pair
                    if (!check.isChecked) null else parseMoney(amount.text.toString())?.takeIf { it > 0.0 }?.let { market to it }
                }
                val sumAlloc = selected.sumOf { it.second }
                if (totalCapital <= 0.0 || selected.isEmpty() || selected.size > 3 || sumAlloc > totalCapital + 1e-6) {
                    Toast.makeText(activity, "Periksa total modal dan 1–3 alokasi coin. Total alokasi harus ≤ total modal.", Toast.LENGTH_LONG).show()
                    return@setOnClickListener
                }
                val manual = manualSwitch.isChecked
                val sl = parsePercent(slField.text.toString()) ?: 0.0
                val tp = parsePercent(tpField.text.toString()) ?: 0.0
                if (manual && (sl < 0.0 || tp <= sl)) {
                    Toast.makeText(activity, "TP manual harus > SL manual. SL 0% diperbolehkan.", Toast.LENGTH_LONG).show()
                    return@setOnClickListener
                }
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                prefs.edit()
                    .putString("total_capital", totalCapital.toString())
                    .putString("mode", modeSpinner.selectedItem.toString())
                    .putBoolean("manual_risk", manual)
                    .putString("manual_sl", sl.toString())
                    .putString("manual_tp", tp.toString())
                    .putString("risk_basis", basisMode.name)
                    .apply()
                val allocations = selected.joinToString(";") { "${it.first}=${it.second}" }
                sendService(activity, MireiForegroundService.ACTION_START) {
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations)
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, selected.first().first)
                    putExtra(MireiForegroundService.EXTRA_EXCHANGE, "indodax")
                    putExtra(MireiForegroundService.EXTRA_TOTAL_CAPITAL, totalCapital)
                }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun showTopUpDialog(activity: Activity) {
        val field = moneyField(activity, 0.0)
        AlertDialog.Builder(activity)
            .setTitle("TOP UP PAPER")
            .setMessage("Tambahkan dana ke kas paper tanpa menghapus 3 posisi yang sedang aktif. Dana akan tersedia untuk siklus berikutnya.")
            .setView(field)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("TOP UP") { _, _ ->
                val amount = parseMoney(field.text.toString()) ?: 0.0
                if (amount <= 0.0) Toast.makeText(activity, "Nominal top up harus > 0.", Toast.LENGTH_SHORT).show()
                else sendService(activity, MireiForegroundService.ACTION_TOP_UP) { putExtra(MireiForegroundService.EXTRA_TOP_UP_AMOUNT, amount) }
            }
            .show()
    }

    private fun showCalculator(activity: Activity) {
        val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(22, 10, 22, 8) }
        val entry = numberField(activity, "Entry price", 100.0)
        val positionCapital = moneyField(activity, 50_000.0)
        val referenceCapital = moneyField(activity, 50_000.0)
        val tp = percentField(activity, 1.0, "TP %")
        val sl = percentField(activity, 0.5, "SL %")
        listOf(label(activity, "Entry price", true), entry, label(activity, "Modal posisi", true), positionCapital, label(activity, "Modal acuan awal", true), referenceCapital, label(activity, "TP %", true), tp, label(activity, "SL %", true), sl).forEach { box.addView(it, spacedParams(6)) }
        val result = label(activity, "Masukan nilai untuk menghitung.", false)
        box.addView(result, spacedParams(12))
        AlertDialog.Builder(activity).setTitle("CALCULATOR TP / SL").setView(box).setNegativeButton("TUTUP", null).setPositiveButton("HITUNG") { _, _ ->
            val entryPrice = parseNumber(entry.text.toString()) ?: 0.0
            val stake = parseMoney(positionCapital.text.toString()) ?: 0.0
            val capital = parseMoney(referenceCapital.text.toString()) ?: 0.0
            val tpPct = parsePercent(tp.text.toString()) ?: 0.0
            val slPct = parsePercent(sl.text.toString()) ?: 0.0
            if (entryPrice > 0.0 && stake > 0.0 && capital > 0.0 && tpPct > 0.0 && slPct >= 0.0) {
                val qty = stake / entryPrice
                val tpEntry = entryPrice * (1.0 + tpPct / 100.0)
                val slEntry = if (slPct == 0.0) 0.0 else entryPrice * (1.0 - slPct / 100.0)
                val tpCapital = entryPrice + (capital * tpPct / 100.0) / qty
                val slCapital = if (slPct == 0.0) 0.0 else entryPrice - (capital * slPct / 100.0) / qty
                result.text = "ENTRY BASIS\nTP ${money(tpEntry)} · SL ${if (slEntry == 0.0) "UNLIMITED" else money(slEntry)}\n\nINITIAL CAPITAL BASIS\nTP ${money(tpCapital)} · SL ${if (slCapital == 0.0) "UNLIMITED" else money(slCapital)}\n\nQty ${"%.8f".format(Locale.US, qty)}"
                result.setTextColor(Color.WHITE)
            } else result.text = "Input belum valid."
        }.show()
    }

    private fun showGlossary(activity: Activity) {
        val scroll = ScrollView(activity)
        val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 14, 18, 16) }
        TradingGlossary.terms.forEach { term -> box.addView(card(activity, "${term.term}\n${term.definition}", 12.5f), spacedParams(6)) }
        scroll.addView(box)
        AlertDialog.Builder(activity).setTitle("KAMUS TRADING · COMPOUNDING · SCALPING").setView(scroll).setPositiveButton("TUTUP", null).show()
    }

    private fun showTradingUniverse(activity: Activity) {
        val rows = TradingUniverse.instruments
        val table = TableLayout(activity).apply { isStretchAllColumns = false; setPadding(10, 8, 10, 10) }
        table.addView(tableRow(activity, listOf("CLASS", "INSTRUMENT", "PROVIDER", "STATUS"), true))
        rows.forEach { item ->
            val providers = item.providers.joinToString(", ")
            val status = if (item.liveAdapterReady) "READY · PAPER" else "CONNECTOR CATALOG"
            table.addView(tableRow(activity, listOf(item.assetClass.label, item.symbol, providers, status), false))
        }
        val scroll = ScrollView(activity); scroll.addView(table)
        AlertDialog.Builder(activity)
            .setTitle("JENIS TRADING & CONNECTOR")
            .setMessage("Alpaca menyediakan API trading saham dan crypto serta paper trading. OANDA menyediakan API untuk currency, metals, dan CFD. Mirei build ini menjaga runtime aktif tetap Indodax paper sampai adapter provider tambahan diaktifkan.")
            .setView(scroll)
            .setPositiveButton("TUTUP", null)
            .show()
    }

    private fun contentOf(activity: MainActivity): LinearLayout? = runCatching { MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(activity) as LinearLayout }.getOrNull()
    private fun currentContent(activity: MainActivity): ViewGroup? = contentOf(activity)
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

    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { line ->
        line.split('|').mapNotNull { part -> val idx = part.indexOf('='); if (idx > 0) part.substring(0, idx) to part.substring(idx + 1) else null }.toMap()
    }

    private fun tableRow(context: Context, values: List<String>, header: Boolean): TableRow {
        val row = TableRow(context).apply { setPadding(0, if (header) 8 else 4, 0, if (header) 8 else 4) }
        values.forEach { value ->
            val tv = cell(context, value)
            if (header) { tv.setTypeface(tv.typeface, android.graphics.Typeface.BOLD); tv.setTextColor(Color.LTGRAY) }
            row.addView(tv)
        }
        return row
    }

    private fun cell(context: Context, value: String): TextView = TextView(context).apply { text = value; textSize = 11f; setTextColor(Color.WHITE); setPadding(6, 7, 6, 7); minWidth = 76 }
    private fun actionButton(context: Context, text: String, enabled: Boolean, onClick: () -> Unit): Button = Button(context).apply { this.text = text; isEnabled = enabled; minHeight = 52; setOnClickListener { onClick() }; setPadding(12, 4, 12, 4) }
    private fun addTitle(content: LinearLayout, value: String) { content.addView(label(content.context, value, true), spacedParams(4)) }
    private fun card(context: Context, value: String, size: Float): TextView = TextView(context).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(12, 12, 12, 12); setBackgroundColor(Color.rgb(24, 34, 43)) }
    private fun label(context: Context, value: String, bold: Boolean): TextView = TextView(context).apply { text = value; textSize = if (bold) 17f else 14f; setTextColor(Color.WHITE); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(2, 8, 2, 4) }
    private fun moneyField(context: Context, value: Double): EditText = EditText(context).apply { text = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); setPadding(12, 10, 12, 10); minimumHeight = 52 }
    private fun percentField(context: Context, value: Double, hint: String): EditText = EditText(context).apply { this.hint = hint; setText("%.3f".format(Locale.US, value)); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); setPadding(12, 10, 12, 10); minimumHeight = 52 }
    private fun numberField(context: Context, hint: String, value: Double): EditText = EditText(context).apply { this.hint = hint; setText("%.8f".format(Locale.US, value)); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); setPadding(12, 10, 12, 10); minimumHeight = 52 }
    private fun spacedParams(top: Int = 10): LinearLayout.LayoutParams = LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top; bottomMargin = 4 }
    private fun parseMoney(raw: String): Double? = raw.trim().replace(".", "").replace(",", ".").toDoubleOrNull()
    private fun parseNumber(raw: String): Double? = raw.trim().replace(",", ".").toDoubleOrNull()
    private fun parsePercent(raw: String): Double? = raw.trim().replace(",", ".").toDoubleOrNull()
    private fun signedText(value: Double): String = when { value > 0.000001 -> "+%.3f".format(Locale.US, value); value < -0.000001 -> "%.3f".format(Locale.US, value); else -> "0.000" }
    private fun signedText(raw: String): String = signedText(parse(raw))
    private fun parse(raw: String): Double = raw.replace("+", "").replace("%", "").trim().toDoubleOrNull() ?: 0.0
    private fun directionColor(value: Double): Int = when { value > 0.000001 -> Color.rgb(60, 200, 100); value < -0.000001 -> Color.rgb(235, 85, 85); else -> Color.LTGRAY }
    private fun money(value: Double): String = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)
    private fun signedMoney(value: Double): String = if (value >= 0) "+Rp ${money(value)}" else "-Rp ${money(kotlin.math.abs(value))}"
    private fun formatEpoch(epochMs: Long): String = if (epochMs <= 0L) "—" else java.text.SimpleDateFormat("MM/dd HH:mm:ss", Locale.US).format(java.util.Date(epochMs))
    private fun ageText(opened: Long): String { if (opened <= 0L) return "—"; val seconds = ((System.currentTimeMillis() - opened).coerceAtLeast(0L) / 1000L); return when { seconds < 60 -> "${seconds}s"; seconds < 3600 -> "${seconds / 60}m ${seconds % 60}s"; else -> "${seconds / 3600}h ${(seconds % 3600) / 60}m" } }
    private fun humanExitReason(reason: String?): String = when (reason) { "stop_loss" -> "STOP LOSS"; "take_profit" -> "TAKE PROFIT"; "ai_close" -> "AI CLOSE"; "manual_close_all" -> "MANUAL CLOSE ALL"; else -> reason?.replace('_', ' ') ?: "—" }
    private fun humanEventType(type: String): String = when (type) { "OPEN" -> "OPEN"; "RE_ENTRY" -> "RE-ENTRY"; "SL_CLOSE" -> "SL CLOSE"; "TP_CLOSE" -> "TP CLOSE"; "MANUAL_CLOSE" -> "MANUAL CLOSE"; "TOP_UP" -> "TOP UP"; "SESSION_STOPPED" -> "STOP"; "SESSION_PAUSED" -> "HOLD"; "SESSION_CLOSED" -> "CLOSE ALL"; "RUNTIME_ERROR" -> "DAMAGE"; else -> type.replace('_', ' ') }
    private fun humanAuditDetails(details: String): String { return details.replace('|', '·').replace("balance_before=", "before=").replace("balance_after=", "after=") }

    private fun statusIndicator(intent: Intent): String {
        val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE).orEmpty()
        val internet = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
        return when {
            state == "CLOSE_ALL" -> "⚪ CLOSE ALL"
            state == "ERROR" -> "🔴 DAMAGE"
            !internet -> "🔵 SEARCHING CONNECTION"
            state == "HOLD" || state == "STOP" -> "🟡 STOPPED / HOLD"
            state == "RUNNING" -> "🟢 RUNNING"
            else -> "🟡 ${state.ifBlank { "STOPPED / HOLD" }}"
        }
    }

    private fun sendService(activity: Activity, action: String, extras: Intent.() -> Unit = {}) {
        val intent = Intent(activity, MireiForegroundService::class.java).apply { this.action = action; extras() }
        runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) }
    }

    private fun findButtons(view: View): List<Button> { if (view is Button) return listOf(view); if (view !is ViewGroup) return emptyList(); return buildList { for (index in 0 until view.childCount) addAll(findButtons(view.getChildAt(index))) } }

    companion object {
        private val TAG_PATCHED = Any()
        private val TAG_OBSERVER = Any()
        private const val STATUS_TAG = "mirei-status"
    }
}
