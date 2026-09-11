package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.app.Application
import android.content.ContentProvider
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.graphics.Color
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.runtime.IndodaxMarketDataSource
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Re-applies only the requested persistent PR19 UI controls after MainActivity redraws. */
class MireiFinalUiEnhancementsProvider : ContentProvider() {
    override fun onCreate(): Boolean {
        val app = context?.applicationContext as? Application ?: return false
        app.registerActivityLifecycleCallbacks(object : Application.ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) { if (activity is MainActivity) install(activity) }
            override fun onActivityCreated(activity: Activity, state: android.os.Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, state: android.os.Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) = Unit
        })
        return true
    }

    private fun install(activity: MainActivity) {
        val root = activity.window.decorView
        if (root.tag == ROOT_TAG) return
        root.tag = ROOT_TAG
        root.viewTreeObserver.addOnGlobalLayoutListener { root.post { patchResume(activity); patchMenu(activity) } }
        root.post { patchResume(activity); patchMenu(activity) }
    }

    private fun patchResume(activity: Activity) {
        val root = activity.window.decorView
        val start = findButtons(root).firstOrNull { it.text?.toString() == "MULAI" } ?: return
        val intent = currentIntent(activity) ?: return
        val resumable = MireiResumePolicy.canResume(intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L))
        val parent = start.parent as? ViewGroup ?: return
        val resume = (0 until parent.childCount).map { parent.getChildAt(it) }.firstOrNull { it.tag == RESUME_TAG } as? Button
        if (!resumable) { resume?.visibility = View.GONE; return }
        val button = resume ?: Button(activity).apply {
            tag = RESUME_TAG
            text = "LANJUTKAN"
            isAllCaps = false
            setOnClickListener { confirmResume(activity) }
        }.also { parent.addView(it, 0, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)) }
        button.visibility = View.VISIBLE
    }

    private fun confirmResume(activity: Activity) {
        val i = currentIntent(activity) ?: return
        val money = ::money
        AlertDialog.Builder(activity)
            .setTitle("LANJUTKAN SESI PAPER")
            .setMessage(
                "Mirei melanjutkan sesi tersimpan, bukan membuat sesi baru.\n\n" +
                    "Coin utama: ${i.getStringExtra(MireiForegroundService.EXTRA_SYMBOL).orEmpty().ifBlank { "—" }}\n" +
                    "Posisi aktif: ${i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}\n" +
                    "Kas tersimpan: ${money(i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n" +
                    "Nilai akun: ${money(i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n" +
                    "Sesi dibuat: ${formatEpoch(i.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L))}\n\n" +
                    "Modal, posisi, PnL, decision counter, dan acuan modal yang tersimpan tetap digunakan."
            )
            .setNegativeButton("BATAL", null)
            .setPositiveButton("LANJUTKAN") { _, _ -> sendStart(activity) }
            .show()
    }

    private fun patchMenu(activity: MainActivity) {
        val menu = findMenuSpinner(activity.window.decorView) ?: return
        when (menu.selectedItem?.toString()) {
            "PASAR" -> patchMarket(activity)
            "POSISI" -> patchPositions(activity)
        }
    }

    private fun patchMarket(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        if (content.getChildAt(0)?.tag == MARKET_TAG) return
        val i = currentIntent(activity) ?: return
        val scanner = parseScanner(i.getStringExtra(MireiForegroundService.EXTRA_SCANNER).orEmpty())
        val symbols = scanner.map { it.symbol }.distinct().ifEmpty { MireiForegroundService.SUPPORTED_MARKETS }
        if (symbols.isEmpty()) return
        val prefs = activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val saved = prefs.getString(KEY_MARKET, null)
        val initial = saved?.takeIf { it in symbols } ?: i.getStringExtra(MireiForegroundService.EXTRA_SYMBOL)?.takeIf { it in symbols } ?: symbols.first()
        content.removeAllViews()
        content.addView(TextView(activity).apply { tag = MARKET_TAG; visibility = View.GONE })
        title(content, "PASAR · MARKET PULSE")
        content.addView(card(activity, "Selector coin tetap terlihat dan pilihannya disimpan.", 12.5f))
        val selector = Spinner(activity)
        selector.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, symbols)
        selector.setSelection(symbols.indexOf(initial).coerceAtLeast(0))
        content.addView(selector)
        val detail = card(activity, "Memuat $initial…", 14f)
        content.addView(detail)
        title(content, "SCANNER MULTI-COIN")
        scanner.forEach { row -> content.addView(card(activity, "${row.symbol}\nHarga Rp ${row.price}\n1M ${row.change1m}% · Momentum ${row.momentum}% · Trend ${row.trend}% · Porsi volume ${row.volumeShare}%", 13f)) }
        if (scanner.isEmpty()) content.addView(card(activity, "Scanner belum tersedia.", 13f))
        fun load(symbol: String) {
            prefs.edit().putString(KEY_MARKET, symbol).apply()
            detail.text = "MEMUAT $symbol…"
            Thread {
                val snapshot = runCatching { IndodaxMarketDataSource().snapshot(symbol) }.getOrNull()
                val text = snapshot?.let {
                    "${it.symbol}\nHarga Rp ${moneyNumber(it.price)}\n" +
                        "1M ${signed(it.change1mPercent)}% · 5M ${signed(it.change5mPercent)}% · 15M ${signed(it.change15mPercent)}%\n" +
                        "Momentum ${signed(it.momentumPercent)}% · Trend ${signed(it.trendScorePercent)}%\n" +
                        "Flow ${signed(it.tradeFlowPercent)}% · Forecast ${(it.forecastConfidence * 100).toInt()}%\n" +
                        "Spread ${fmt(it.spreadPercent)}%\nData ${if (it.dataFresh) "SEGAR" else "STALE"}\nSnapshot: ${formatEpoch(it.snapshotEpochMs)}"
                } ?: "$symbol\nData market belum tersedia."
                activity.runOnUiThread { if (!activity.isFinishing) detail.text = text }
            }.start()
        }
        selector.setOnItemSelectedListener(object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { symbols.getOrNull(position)?.let(::load) }
        })
        load(initial)
    }

    private fun patchPositions(activity: MainActivity) {
        val content = contentOf(activity) ?: return
        if (content.getChildAt(0)?.tag == POSITION_TAG) return
        val i = currentIntent(activity) ?: return
        val rows = parsePositions(i.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty())
        if (rows.isEmpty()) return
        content.removeAllViews()
        content.addView(TextView(activity).apply { tag = POSITION_TAG; visibility = View.GONE })
        title(content, "POSISI AKTIF")
        rows.forEach { row ->
            val capital = row["risk_capital"].orEmpty().toDoubleOrNull() ?: row["stake"].orEmpty().toDoubleOrNull() ?: 0.0
            val tp = row["target_tp_pct"].orEmpty().toDoubleOrNull() ?: row["tp_pct"].orEmpty().toDoubleOrNull() ?: 0.0
            val sl = row["target_sl_pct"].orEmpty().toDoubleOrNull() ?: row["sl_pct"].orEmpty().toDoubleOrNull() ?: 0.0
            val slText = if (sl == 0.0) "0% — UNLIMITED HOLD sampai TP atau tutup manual" else "${percent(sl)} dari modal acuan"
            content.addView(card(activity,
                "${row["symbol"].orEmpty()}\n" +
                    "Modal posisi: Rp ${moneyNumber(row["stake"].orEmpty().toDoubleOrNull() ?: 0.0)}\n" +
                    "Dasar TP/SL: ${if (row["risk_basis"] == "INITIAL_CAPITAL") "MODAL BELI PERTAMA" else "HARGA ENTRY"}\n" +
                    "Modal acuan: Rp ${moneyNumber(capital)}\n" +
                    "TP: +${percent(tp)} dari modal acuan\n" +
                    "SL: $slText\n\n" +
                    "Harga entry: Rp ${moneyNumber(row["entry"].orEmpty().toDoubleOrNull() ?: 0.0)}\n" +
                    "Harga target TP: Rp ${moneyNumber(row["tp"].orEmpty().toDoubleOrNull() ?: 0.0)}\n" +
                    "Harga target SL: Rp ${moneyNumber(row["sl"].orEmpty().toDoubleOrNull() ?: 0.0)}\n" +
                    "Harga target adalah translasi target modal berdasarkan quantity posisi.\n" +
                    "PnL berjalan: Rp ${row["unrealized"].orEmpty().toDoubleOrNull()?.let(::signedMoney) ?: "0"}", 13.5f))
        }
    }

    private fun sendStart(activity: Activity) {
        val intent = Intent(activity, MireiForegroundService::class.java).setAction(MireiForegroundService.ACTION_START)
        runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) }
    }

    private fun currentIntent(activity: Activity): Intent? = runCatching { MainActivity::class.java.getDeclaredField("currentIntent").apply { isAccessible = true }.get(activity) as? Intent }.getOrNull()
    private fun contentOf(activity: MainActivity): LinearLayout? = runCatching { MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(activity) as LinearLayout }.getOrNull()
    private fun findMenuSpinner(view: View): Spinner? { if (view is Spinner && view.selectedItem?.toString() in MENUS) return view; if (view !is ViewGroup) return null; for (n in 0 until view.childCount) findMenuSpinner(view.getChildAt(n))?.let { return it }; return null }
    private fun findButtons(view: View): List<Button> { if (view is Button) return listOf(view); if (view !is ViewGroup) return emptyList(); return buildList { for (n in 0 until view.childCount) addAll(findButtons(view.getChildAt(n))) } }
    private fun title(content: LinearLayout, value: String) { content.addView(TextView(content.context).apply { text = value; textSize = 18f; setTextColor(Color.WHITE); setPadding(4, 12, 4, 6); setTypeface(typeface, android.graphics.Typeface.BOLD) }) }
    private fun card(context: Context, value: String, size: Float): TextView = TextView(context).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(8, 10, 8, 10); setBackgroundColor(Color.rgb(24, 34, 43)) }
    private fun parsePositions(raw: String): List<Map<String, String>> = raw.lines().filter { it.isNotBlank() }.map { it.split('|').mapNotNull { token -> token.split('=', limit = 2).takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap() }
    private data class ScannerRow(val symbol: String, val price: String, val change1m: String, val momentum: String, val trend: String, val volumeShare: String)
    private fun parseScanner(raw: String): List<ScannerRow> = raw.lines().mapNotNull { line -> val p = line.split('|'); if (p.size >= 6) ScannerRow(p[0], p[1], p[2], p[3], p[4], p[5]) else null }
    private fun money(value: Double): String = "Rp ${moneyNumber(value)}"
    private fun moneyNumber(value: Double): String = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)
    private fun percent(value: Double): String = "%.2f%%".format(Locale.US, value)
    private fun signed(value: Double): String = if (value >= 0) "+%.3f".format(Locale.US, value) else "%.3f".format(Locale.US, value)
    private fun fmt(value: Double): String = "%.3f".format(Locale.US, value)
    private fun signedMoney(value: Double): String = if (value >= 0) "+${moneyNumber(value)}" else "-${moneyNumber(kotlin.math.abs(value))}"
    private fun formatEpoch(epochMs: Long): String = if (epochMs <= 0L) "—" else SimpleDateFormat("MM/dd/HH/mm/ss", Locale.US).format(Date(epochMs))
    override fun query(uri: Uri, projection: Array<String>?, selection: String?, selectionArgs: Array<String>?, sortOrder: String?): Cursor? = null
    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<String>?): Int = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<String>?): Int = 0

    companion object {
        private const val ROOT_TAG = "mirei_final_ui_observer_v1"
        private const val RESUME_TAG = "mirei_resume_button_v1"
        private const val MARKET_TAG = "mirei_market_persistent_v1"
        private const val POSITION_TAG = "mirei_position_risk_v1"
        private const val PREFS = "mirei_ui"
        private const val KEY_MARKET = "persistent_market_symbol"
        private val MENUS = setOf("RINGKASAN", "PASAR", "POSISI", "AKTIVITAS", "KEPUTUSAN", "RISIKO", "EXCHANGE / API", "PENGATURAN", "LOG / AUDIT")
    }
}
