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
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.TradingGlossary
import com.mirei.app.core.TradingUniverse
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.WeakHashMap

/** Presentation-only compatibility layer over Build 194's programmatic MainActivity. */
class MireiUiPatchApplication : Application() {
    private val installed = WeakHashMap<MainActivity, Boolean>()
    private val lastMenu = WeakHashMap<MainActivity, String>()
    private val lastTick = WeakHashMap<MainActivity, Long>()

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) { if (activity is MainActivity) install(activity) }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) = Unit
        })
    }

    private fun install(activity: MainActivity) {
        if (installed[activity] == true) return
        installed[activity] = true
        patchStartButton(activity)
        val root = activity.window.decorView
        if (!root.viewTreeObserver.isAlive) return
        root.viewTreeObserver.addOnGlobalLayoutListener {
            val menu = findMenu(root) ?: return@addOnGlobalLayoutListener
            val selected = menu.selectedItem?.toString().orEmpty()
            val current = currentIntent(activity)
            val tick = current?.getLongExtra(MireiForegroundService.EXTRA_TICK, 0L) ?: 0L
            if (lastMenu[activity] == selected && lastTick[activity] == tick) return@addOnGlobalLayoutListener
            lastMenu[activity] = selected
            lastTick[activity] = tick
            root.post {
                when (selected) {
                    "RINGKASAN" -> renderDashboard(activity)
                    "PASAR" -> renderMarket(activity)
                    "POSISI" -> renderPositions(activity)
                    "LOG / AUDIT" -> renderAudit(activity)
                }
            }
        }
    }

    private fun patchStartButton(activity: MainActivity) {
        val root = activity.window.decorView
        fun scan() {
            findButtons(root).filter { it.text?.toString() == "MULAI" }.forEach { button ->
                if (button.getTag() == START_PATCH_TAG) return@forEach
                button.setTag(START_PATCH_TAG)
                button.setOnClickListener { showStartDialog(activity) }
            }
        }
        scan()
        if (root.viewTreeObserver.isAlive) root.viewTreeObserver.addOnGlobalLayoutListener { scan() }
    }

    private fun renderDashboard(activity: MainActivity) {
        val content = content(activity) ?: return
        val intent = currentIntent(activity) ?: return
        content.removeAllViews()
        addTitle(content, "RINGKASAN · DASHBOARD")
        content.addView(card(activity, statusIndicator(intent), 15f), params(4))
        val sessionStart = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(200).filter { sessionStart == 0L || it.openedAtEpochMs >= sessionStart } }.getOrDefault(emptyList())
        val closed = trades.filter { it.closedAtEpochMs != null }
        val wins = closed.count { it.pnlIdr > 0.0 }
        val winRate = if (closed.isEmpty()) 0.0 else wins * 100.0 / closed.size
        val suggestions = runCatching { db.recentSuggestions(300).filter { sessionStart == 0L || it.createdAtEpochMs >= sessionStart } }.getOrDefault(emptyList())
        val aiBuy = suggestions.count { it.action == "BUY" }
        val aiHold = suggestions.count { it.action == "HOLD" }
        val aiSell = suggestions.count { it.action == "SELL" || it.action == "CLOSE" }
        val actualBuy = trades.count { it.side == "BUY" || it.side == "RE_ENTRY" || it.side == "INITIAL_HOLDING" }
        val actualSell = closed.size
        content.addView(card(activity,
            "EQUITY   Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n" +
                "KAS      Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n" +
                "POSISI   ${intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}/3\n" +
                "WIN RATE ${"%.2f".format(Locale.US, winRate)}%  (${wins}/${closed.size})\n" +
                "MODAL    Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_TOTAL_CAPITAL, 0.0))}", 14f), params(8))
        addTitle(content, "AI VS ACTUAL · SESI INI")
        val table = TableLayout(activity).apply { isStretchAllColumns = true }
        table.addView(tableRow(activity, listOf("SUMBER", "BUY", "HOLD", "SELL"), true))
        table.addView(tableRow(activity, listOf("AI DECISION", aiBuy.toString(), aiHold.toString(), aiSell.toString()), false))
        table.addView(tableRow(activity, listOf("ACTUAL PAPER", actualBuy.toString(), "0", actualSell.toString()), false))
        content.addView(table, params(2))
        content.addView(card(activity, "AI BUY/SELL/HOLD adalah keputusan. Actual hanya dihitung dari ledger OPEN/CLOSE. HOLD actual = 0 karena HOLD bukan order.", 12f), params(6))
        addTitle(content, "KONTROL SESI")
        val controls = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; setPadding(0, 4, 0, 4) }
        controls.addView(actionButton(activity, "LANJUTKAN") { sendService(activity, MireiForegroundService.ACTION_START) })
        controls.addView(actionButton(activity, "TOP UP") { showTopUpDialog(activity) })
        content.addView(controls, params(3))
        addTitle(content, "TOOLS")
        val tools = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER; setPadding(0, 4, 0, 4) }
        tools.addView(actionButton(activity, "KALKULATOR") { showCalculator(activity) })
        tools.addView(actionButton(activity, "KAMUS") { showGlossary(activity) })
        tools.addView(actionButton(activity, "JENIS TRADING") { showTradingUniverse(activity) })
        content.addView(tools, params(3))
        addTitle(content, "3 POSISI")
        renderPositionRowsInto(content, intent, true)
        addTitle(content, "STATUS & LOADING")
        content.addView(card(activity, "🟢 RUNNING · 🔴 DAMAGE · 🟡 STOPPED/HOLD · 🔵 SEARCHING CONNECTION · ⚪ CLOSE ALL\nFungsi yang menunggu market baru menampilkan LOADING/SEARCHING; LANJUTKAN memulihkan cash, posisi, counter, dan market selection yang tersimpan.", 12f), params(6))
        addTitle(content, "MULTI-ASSET CONNECTOR")
        content.addView(card(activity, "Crypto: Indodax / Bybit / OKX. Saham: Alpaca. Forex & komoditas: OANDA. Catalog ditambahkan tanpa mengubah execution path Build 194: runtime paper aktif tetap Indodax sampai adapter provider tambahan diaktifkan.", 12f), params(6))
    }

    private fun renderMarket(activity: MainActivity) {
        val content = content(activity) ?: return
        val intent = currentIntent(activity) ?: return
        content.removeAllViews()
        addTitle(content, "PASAR · MARKET PULSE TABLE")
        val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        val internet = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
        content.addView(card(activity, if (fresh && internet) "🟢 DATA MARKET SEGAR · INDODAX API" else "🔵 LOADING / SEARCHING CONNECTION…", 13f), params(4))
        val rows = parseScanner(intent.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty())
        val table = TableLayout(activity).apply { isStretchAllColumns = false }
        table.addView(tableRow(activity, listOf("COIN", "HARGA", "1M", "MOM", "TREND"), true))
        rows.forEach { row ->
            val tr = TableRow(activity)
            listOf(row.symbol, row.price, signed(row.change1m), signed(row.momentum), signed(row.trend)).forEachIndexed { index, value ->
                val tv = cell(activity, value)
                if (index == 0) tv.setTextColor(directionColor(parseNumber(row.trend)))
                if (index >= 2) tv.setTextColor(directionColor(parseNumber(value)))
                tr.addView(tv)
            }
            table.addView(tr)
        }
        content.addView(table, params(4))
        addTitle(content, "SUGESTI MIREI · BERDASARKAN EXCHANGE AKTIF")
        rows.sortedByDescending { parseNumber(it.trend) * 0.5 + parseNumber(it.momentum) * 0.3 + parseNumber(it.change1m) * 0.2 }.take(3).forEachIndexed { index, row ->
            content.addView(card(activity, "${index + 1}. ${row.symbol}\nTrend ${signed(row.trend)}% · Momentum ${signed(row.momentum)}% · 1M ${signed(row.change1m)}%\nSumber: scanner Indodax dari API pada sesi ini.", 12f), params(4))
        }
        content.addView(card(activity, "Warna: 🟢 naik · 🔴 turun · ⚪ flat. Hanya nama coin/nilai terkait yang berubah warna. Grafik market pulse dihapus.", 12f), params(4))
    }

    private fun renderPositions(activity: MainActivity) {
        val content = content(activity) ?: return
        val intent = currentIntent(activity) ?: return
        content.removeAllViews()
        addTitle(content, "POSISI · 3 SLOT REAL-TIME")
        val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        content.addView(card(activity, if (fresh) "🟢 MARKET TERBARU" else "🔵 LOADING MARKET TERBARU…", 13f), params(4))
        renderPositionRowsInto(content, intent, true)
    }

    private fun renderPositionRowsInto(content: LinearLayout, intent: Intent, showHeader: Boolean) {
        val rows = parsePositions(intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        val table = TableLayout(content.context).apply { isStretchAllColumns = false }
        if (showHeader) table.addView(tableRow(content.context, listOf("#", "COIN", "MODAL", "ENTRY", "NOW", "TP", "SL", "UNREALIZED", "UMUR"), true))
        for (slot in 0 until 3) {
            val p = rows.getOrNull(slot)
            if (p == null) {
                table.addView(tableRow(content.context, listOf("${slot + 1}", "EMPTY", "—", "—", "—", "—", "—", "—", "—"), false))
                continue
            }
            val entryPrice = p["entry"]?.toDoubleOrNull() ?: 0.0
            val stake = p["stake"]?.toDoubleOrNull() ?: 0.0
            val now = p["current"]?.toDoubleOrNull() ?: entryPrice
            val tp = p["tp"]?.toDoubleOrNull() ?: entryPrice
            val sl = p["sl"]?.toDoubleOrNull() ?: 0.0
            val referenceCapital = p["risk_capital"]?.toDoubleOrNull()?.takeIf { it > 0.0 } ?: stake
            val qty = if (entryPrice > 0) stake / entryPrice else 0.0
            val tpEntryPct = p["tp_pct"]?.toDoubleOrNull() ?: 0.0
            val slEntryPct = p["sl_pct"]?.toDoubleOrNull() ?: 0.0
            val tpCapitalPct = if (referenceCapital > 0 && qty > 0) ((tp - entryPrice) * qty / referenceCapital) * 100.0 else 0.0
            val slCapitalPct = if (sl == 0.0 || referenceCapital <= 0 || qty <= 0) 0.0 else ((sl - entryPrice) * qty / referenceCapital) * 100.0
            val values = listOf(
                "${slot + 1}", p["symbol"].orEmpty(), money(stake), money(entryPrice), money(now),
                "${money(tp)} (${signed(tpEntryPct)}% entry / +${"%.3f".format(Locale.US, tpCapitalPct)}% modal)",
                if (sl == 0.0) "UNLIMITED" else "${money(sl)} (${signed(slEntryPct)}% entry / ${"%.3f".format(Locale.US, slCapitalPct)}% modal)",
                signedMoney(p["unrealized"]?.toDoubleOrNull() ?: 0.0), ageText(p["opened"]?.toLongOrNull() ?: 0L),
            )
            table.addView(tableRow(content.context, values, false))
        }
        content.addView(table, params(3))
        content.addView(card(content.context, "TP/SL entry = target relatif terhadap harga entry. TP/SL modal = perhitungan real terhadap modal acuan yang tersimpan pada posisi, bukan hardcode.", 12f), params(4))
    }

    private fun renderAudit(activity: MainActivity) {
        val content = content(activity) ?: return
        val intent = currentIntent(activity) ?: return
        content.removeAllViews()
        addTitle(content, "LOG / AUDIT · SESI INI")
        val start = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(200).filter { start == 0L || it.openedAtEpochMs >= start } }.getOrDefault(emptyList())
        val closed = trades.filter { it.closedAtEpochMs != null }
        val wins = closed.count { it.pnlIdr > 0.0 }
        val rate = if (closed.isEmpty()) 0.0 else wins * 100.0 / closed.size
        content.addView(card(activity, "CLOSE nyata ${closed.size} · WIN RATE ${"%.2f".format(Locale.US, rate)}%\nAI BUY ${intent.getIntExtra(MireiForegroundService.EXTRA_BUY_COUNT, 0)} · HOLD ${intent.getIntExtra(MireiForegroundService.EXTRA_HOLD_COUNT, 0)} · SELL ${intent.getIntExtra(MireiForegroundService.EXTRA_SELL_COUNT, 0)}", 13f), params(4))
        val table = TableLayout(activity).apply { isStretchAllColumns = false }
        table.addView(tableRow(activity, listOf("WAKTU", "EVENT", "COIN", "STATUS", "PNL", "DETAIL"), true))
        trades.forEach { trade ->
            val status = if (trade.closedAtEpochMs == null) "OPEN" else "CLOSE"
            val event = if (status == "OPEN") trade.entryReason else exitLabel(trade.exitReason)
            val detail = "entry ${trade.entryPrice?.let { money(it) } ?: "—"} → exit ${trade.exitPrice?.let { money(it) } ?: "—"}"
            table.addView(tableRow(activity, listOf(formatEpoch(trade.closedAtEpochMs ?: trade.openedAtEpochMs), event, trade.symbol, status, signedMoney(trade.pnlIdr), detail), false))
        }
        runCatching { db.recentAudit(120).filter { start == 0L || it.createdAtEpochMs >= start } }.getOrDefault(emptyList()).forEach { audit ->
            table.addView(tableRow(activity, listOf(formatEpoch(audit.createdAtEpochMs), audit.eventType.replace('_', ' '), "—", "ENGINE", "—", audit.details.replace('|', '·')), false))
        }
        content.addView(table, params(4))
        content.addView(card(activity, "Audit sekarang berbentuk tabel kronologis. SELL decision hanya keputusan AI; CLOSE nyata hanya berasal dari trade ledger.", 12f), params(4))
    }

    private fun showStartDialog(activity: MainActivity) {
        val prefs = activity.getSharedPreferences("mirei_settings", Context.MODE_PRIVATE)
        val savedCapital = prefs.getString("total_capital", null)?.toDoubleOrNull()?.takeIf { it > 0.0 } ?: 150_000.0
        val scroll = ScrollView(activity).apply { setPadding(10, 10, 10, 22) }
        val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 12, 18, 24) }
        scroll.addView(box)
        box.addView(label(activity, "DANA PAPER AWAL / TOTAL MODAL", true), params(2))
        val totalCapital = moneyField(activity, savedCapital)
        box.addView(totalCapital, params(8))
        box.addView(card(activity, "Bukan lagi hardcode Rp150.000. Nominal ini menjadi modal acuan sesi dan dapat ditambah lewat TOP UP.", 12f), params(6))
        box.addView(label(activity, "ALOKASI 1–3 COIN", true), params(10))
        box.addView(label(activity, "Total seluruh alokasi harus <= modal sesi.", false), params(2))
        val selectedRows = mutableListOf<Pair<CheckBox, EditText>>()
        val marketContainer = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(4, 3, 4, 10) }
        val allocationDefault = savedCapital / 3.0
        MireiForegroundService.SUPPORTED_MARKETS.forEachIndexed { index, market ->
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(8, 8, 8, 8) }
            val check = CheckBox(activity).apply { text = market; textSize = 15f; isChecked = index < 3 }
            val amount = moneyField(activity, if (index < 3) allocationDefault else 0.0).apply { isEnabled = check.isChecked; if (!check.isChecked) setText("") }
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked; if (!checked) amount.setText("") }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(amount, LinearLayout.LayoutParams(150, ViewGroup.LayoutParams.WRAP_CONTENT))
            marketContainer.addView(row, params(5))
            selectedRows += check to amount
        }
        box.addView(marketContainer)
        box.addView(label(activity, "MODE TRADING", true), params(8))
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        val mode = Spinner(activity).apply { adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, modes); setSelection(modes.indexOf(prefs.getString("mode", "BALANCED")).coerceAtLeast(0)) }
        box.addView(mode, params(6))
        box.addView(label(activity, "DASAR TP / SL", true), params(8))
        val basis = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL; setPadding(5, 2, 5, 2) }
        val entry = RadioButton(activity).apply { id = View.generateViewId(); text = "ENTRY PRICE"; textSize = 15f; setPadding(0, 7, 0, 7) }
        val initial = RadioButton(activity).apply { id = View.generateViewId(); text = "INITIAL CAPITAL / MODAL ACUAN"; textSize = 15f; setPadding(0, 7, 0, 7) }
        basis.addView(entry); basis.addView(initial)
        basis.check(if (prefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name) == RiskReferenceMode.INITIAL_CAPITAL.name) initial.id else entry.id)
        box.addView(basis, params(5))
        box.addView(label(activity, "TP / SL MANUAL", true), params(8))
        val manual = Switch(activity).apply { text = "Gunakan TP/SL manual"; isChecked = prefs.getBoolean("manual_risk", false); setPadding(7, 6, 7, 6) }
        box.addView(manual, params(4))
        val riskBox = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; setPadding(2, 2, 2, 2) }
        val sl = percentField(activity, prefs.getString("manual_sl", "0.000")?.toDoubleOrNull() ?: 0.0, "SL %")
        val tp = percentField(activity, prefs.getString("manual_tp", "1.000")?.toDoubleOrNull() ?: 1.0, "TP %")
        riskBox.addView(sl, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 10 })
        riskBox.addView(tp, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        riskBox.visibility = if (manual.isChecked) View.VISIBLE else View.GONE
        manual.setOnCheckedChangeListener { _, checked -> riskBox.visibility = if (checked) View.VISIBLE else View.GONE; mode.isEnabled = !checked }
        box.addView(riskBox, params(4))
        box.addView(card(activity, "SL 0% = unlimited hold sampai TP atau tutup manual.", 12f), params(6))

        val dialog = AlertDialog.Builder(activity).setTitle("MULAI SESI PAPER").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.window?.apply { setLayout((activity.resources.displayMetrics.widthPixels * 0.94f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.92f).toInt()); setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE) }
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).minHeight = 56
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).minHeight = 56
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val capital = parseMoney(totalCapital.text.toString()) ?: 0.0
                val allocations = selectedRows.mapNotNull { (check, field) -> if (!check.isChecked) null else parseMoney(field.text.toString())?.takeIf { it > 0.0 }?.let { check.text.toString() to it } }
                val sum = allocations.sumOf { it.second }
                val manualOn = manual.isChecked
                val slValue = parsePercent(sl.text.toString()) ?: 0.0
                val tpValue = parsePercent(tp.text.toString()) ?: 0.0
                if (capital <= 0 || allocations.isEmpty() || allocations.size > 3 || sum > capital + 1e-6 || (manualOn && tpValue <= slValue)) {
                    Toast.makeText(activity, "Periksa modal, alokasi 1–3 coin, dan TP/SL. Total alokasi harus <= modal.", Toast.LENGTH_LONG).show()
                    return@setOnClickListener
                }
                val basisMode = if (basis.checkedRadioButtonId == initial.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                prefs.edit().putString("total_capital", capital.toString()).putString("mode", mode.selectedItem.toString()).putBoolean("manual_risk", manualOn).putString("manual_sl", slValue.toString()).putString("manual_tp", tpValue.toString()).putString("risk_basis", basisMode.name).apply()
                sendService(activity, MireiForegroundService.ACTION_START) {
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations.joinToString(";") { "${it.first}=${it.second}" })
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, allocations.first().first)
                    putExtra(MireiForegroundService.EXTRA_EXCHANGE, "indodax")
                }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun showTopUpDialog(activity: MainActivity) {
        val field = moneyField(activity, 0.0)
        AlertDialog.Builder(activity).setTitle("TOP UP PAPER").setMessage("Tambahkan dana tanpa menghapus posisi yang sudah berjalan.").setView(field).setNegativeButton("BATAL", null).setPositiveButton("TOP UP") { _, _ ->
            val amount = parseMoney(field.text.toString()) ?: 0.0
            if (amount > 0) sendService(activity, MireiForegroundService.ACTION_TOP_UP) { putExtra(MireiForegroundService.EXTRA_TOP_UP_AMOUNT, amount) } else Toast.makeText(activity, "Nominal top up harus > 0", Toast.LENGTH_SHORT).show()
        }.show()
    }

    private fun showCalculator(activity: MainActivity) {
        val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 10, 18, 12) }
        val entry = numberField(activity, "Entry price", 100.0)
        val stake = moneyField(activity, 50_000.0)
        val reference = moneyField(activity, 50_000.0)
        val tp = percentField(activity, 1.0, "TP %")
        val sl = percentField(activity, 0.5, "SL %")
        listOf(label(activity, "Entry price", true), entry, label(activity, "Modal posisi", true), stake, label(activity, "Modal acuan awal", true), reference, label(activity, "TP %", true), tp, label(activity, "SL %", true), sl).forEach { box.addView(it, params(5)) }
        val result = label(activity, "Tekan HITUNG.", false); box.addView(result, params(10))
        AlertDialog.Builder(activity).setTitle("CALCULATOR TP / SL").setView(box).setNegativeButton("TUTUP", null).setPositiveButton("HITUNG") { _, _ ->
            val e = parseNumber(entry.text.toString()) ?: 0.0
            val s = parseMoney(stake.text.toString()) ?: 0.0
            val c = parseMoney(reference.text.toString()) ?: 0.0
            val tpPct = parsePercent(tp.text.toString()) ?: 0.0
            val slPct = parsePercent(sl.text.toString()) ?: 0.0
            if (e > 0 && s > 0 && c > 0 && tpPct > 0 && slPct >= 0) {
                val qty = s / e
                val tpEntry = e * (1 + tpPct / 100)
                val slEntry = if (slPct == 0.0) 0.0 else e * (1 - slPct / 100)
                val tpCapital = e + (c * tpPct / 100) / qty
                val slCapital = if (slPct == 0.0) 0.0 else e - (c * slPct / 100) / qty
                result.text = "ENTRY BASIS\nTP ${money(tpEntry)} · SL ${if (slEntry == 0.0) "UNLIMITED" else money(slEntry)}\n\nINITIAL CAPITAL BASIS\nTP ${money(tpCapital)} · SL ${if (slCapital == 0.0) "UNLIMITED" else money(slCapital)}"
            }
        }.show()
    }

    private fun showGlossary(activity: MainActivity) {
        val scroll = ScrollView(activity); val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(18, 12, 18, 16) }
        TradingGlossary.terms.forEach { box.addView(card(activity, "${it.term}\n${it.definition}", 12f), params(5)) }
        scroll.addView(box)
        AlertDialog.Builder(activity).setTitle("KAMUS TRADING · COMPOUNDING · SCALPING").setView(scroll).setPositiveButton("TUTUP", null).show()
    }

    private fun showTradingUniverse(activity: MainActivity) {
        val table = TableLayout(activity).apply { isStretchAllColumns = false }
        table.addView(tableRow(activity, listOf("CLASS", "INSTRUMENT", "PROVIDER", "STATUS"), true))
        TradingUniverse.instruments.forEach { item -> table.addView(tableRow(activity, listOf(item.assetClass.label, item.symbol, item.providers.joinToString(", "), if (item.liveAdapterReady) "READY · PAPER" else "CATALOG"), false)) }
        val scroll = ScrollView(activity).apply { addView(table) }
        AlertDialog.Builder(activity).setTitle("JENIS TRADING & CONNECTOR").setMessage("Alpaca: saham/crypto. OANDA: forex/metals/CFD. Runtime paper aktif saat ini tetap menggunakan Indodax untuk menjaga jalur Build 194.").setView(scroll).setPositiveButton("TUTUP", null).show()
    }

    private data class ScannerRow(val symbol: String, val price: String, val change1m: String, val momentum: String, val trend: String)
    private fun parseScanner(raw: String): List<ScannerRow> = raw.lines().mapNotNull { line -> val p = line.split('|'); if (p.size >= 5) ScannerRow(p[0], p[1], p[2], p[3], p[4]) else null }
    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { line -> line.split('|').mapNotNull { part -> val i = part.indexOf('='); if (i > 0) part.substring(0, i) to part.substring(i + 1) else null }.toMap() }
    private fun content(activity: MainActivity): LinearLayout? = runCatching { MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(activity) as LinearLayout }.getOrNull()
    private fun currentIntent(activity: MainActivity): Intent? = runCatching { MainActivity::class.java.getDeclaredField("currentIntent").apply { isAccessible = true }.get(activity) as? Intent }.getOrNull()
    private fun findMenu(view: View): Spinner? {
        if (view is Spinner) {
            val value = view.selectedItem?.toString().orEmpty()
            if (value in setOf("RINGKASAN", "PASAR", "POSISI", "LOG / AUDIT", "AKTIVITAS", "KEPUTUSAN", "RISIKO", "EXCHANGE / API", "PENGATURAN")) return view
        }
        if (view !is ViewGroup) return null
        for (i in 0 until view.childCount) findMenu(view.getChildAt(i))?.let { return it }
        return null
    }
    private fun findButtons(view: View): List<Button> {
        if (view is Button) return listOf(view)
        if (view !is ViewGroup) return emptyList()
        return buildList { for (i in 0 until view.childCount) addAll(findButtons(view.getChildAt(i))) }
    }
    private fun addTitle(content: LinearLayout, text: String) { content.addView(label(content.context, text, true), params(4)) }
    private fun label(context: Context, text: String, bold: Boolean) = TextView(context).apply { this.text = text; textSize = if (bold) 17f else 14f; setTextColor(Color.WHITE); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(2, 7, 2, 3) }
    private fun card(context: Context, text: String, size: Float) = TextView(context).apply { this.text = text; textSize = size; setTextColor(Color.WHITE); setPadding(12, 12, 12, 12); setBackgroundColor(Color.rgb(24, 34, 43)) }
    private fun actionButton(context: Context, text: String, click: () -> Unit) = Button(context).apply { this.text = text; minHeight = 52; setOnClickListener { click() } }
    private fun cell(context: Context, text: String) = TextView(context).apply { this.text = text; textSize = 11f; setTextColor(Color.WHITE); setPadding(6, 7, 6, 7); minWidth = 74 }
    private fun tableRow(context: Context, values: List<String>, header: Boolean): TableRow = TableRow(context).apply { values.forEach { value -> val tv = cell(context, value); if (header) { tv.setTypeface(tv.typeface, android.graphics.Typeface.BOLD); tv.setTextColor(Color.LTGRAY) }; addView(tv) } }
    private fun params(top: Int = 0) = LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top; bottomMargin = 4 }
    private fun moneyField(context: Context, value: Double) = EditText(context).apply { setText(NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); minimumHeight = 52; setPadding(12, 10, 12, 10) }
    private fun percentField(context: Context, value: Double, hintText: String) = EditText(context).apply { hint = hintText; setText("%.3f".format(Locale.US, value)); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); minimumHeight = 52; setPadding(12, 10, 12, 10) }
    private fun numberField(context: Context, hintText: String, value: Double) = EditText(context).apply { hint = hintText; setText("%.8f".format(Locale.US, value)); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); minimumHeight = 52; setPadding(12, 10, 12, 10) }
    private fun parseMoney(raw: String): Double? = raw.trim().replace(".", "").replace(",", ".").toDoubleOrNull()
    private fun parsePercent(raw: String): Double? = raw.trim().replace(",", ".").toDoubleOrNull()
    private fun parseNumber(raw: String): Double? = raw.trim().replace(",", ".").toDoubleOrNull()
    private fun parseNumber(raw: String): Double = raw.replace("+", "").replace("%", "").trim().replace(",", ".").toDoubleOrNull() ?: 0.0
    private fun signed(value: Double): String = when { value > 0.000001 -> "+%.3f".format(Locale.US, value); value < -0.000001 -> "%.3f".format(Locale.US, value); else -> "0.000" }
    private fun signed(raw: String): String = signed(parseNumber(raw))
    private fun directionColor(value: Double): Int = when { value > 0.000001 -> Color.rgb(60, 200, 100); value < -0.000001 -> Color.rgb(235, 85, 85); else -> Color.LTGRAY }
    private fun money(value: Double): String = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)
    private fun signedMoney(value: Double): String = if (value >= 0) "+Rp ${money(value)}" else "-Rp ${money(kotlin.math.abs(value))}"
    private fun formatEpoch(ms: Long): String = if (ms <= 0) "—" else SimpleDateFormat("MM/dd HH:mm:ss", Locale.US).format(Date(ms))
    private fun ageText(opened: Long): String { if (opened <= 0) return "—"; val seconds = ((System.currentTimeMillis() - opened).coerceAtLeast(0L) / 1000L); return when { seconds < 60 -> "${seconds}s"; seconds < 3600 -> "${seconds / 60}m ${seconds % 60}s"; else -> "${seconds / 3600}h ${(seconds % 3600) / 60}m" } }
    private fun exitLabel(reason: String?): String = when (reason) { "take_profit" -> "TAKE PROFIT"; "stop_loss" -> "STOP LOSS"; "manual_close_all" -> "MANUAL CLOSE ALL"; "ai_close" -> "AI CLOSE"; else -> reason?.replace('_', ' ') ?: "CLOSE" }
    private fun statusIndicator(intent: Intent): String { val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE).orEmpty(); val internet = intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false); return when { state == "CLOSE_ALL" -> "⚪ CLOSE ALL"; state == "ERROR" -> "🔴 DAMAGE"; !internet -> "🔵 SEARCHING CONNECTION"; state == "HOLD" || state == "STOP" -> "🟡 STOPPED / HOLD"; state == "RUNNING" -> "🟢 RUNNING"; else -> "🟡 ${state.ifBlank { "STOPPED / HOLD" }}" } }
    private fun sendService(activity: MainActivity, action: String, extras: Intent.() -> Unit = {}) { val intent = Intent(activity, MireiForegroundService::class.java).apply { this.action = action; extras() }; runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) } }
    companion object { private val START_PATCH_TAG = Any() }
}
