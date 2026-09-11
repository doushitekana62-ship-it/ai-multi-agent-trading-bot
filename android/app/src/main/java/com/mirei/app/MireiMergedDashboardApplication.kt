package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.app.Application
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TableLayout
import android.widget.TableRow
import android.widget.TextView
import android.widget.Toast
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.MireiDatabase
import java.text.NumberFormat
import java.util.Locale
import java.util.WeakHashMap

/**
 * Stable merged presentation layer.
 * MainActivity owns its original content/menu; the dashboard is a sibling of that content
 * inside the ScrollView wrapper, so MainActivity.removeAllViews() can never delete or race it.
 */
class MireiMergedDashboardApplication : Application() {
    private val installed = WeakHashMap<MainActivity, Boolean>()
    private val wrappers = WeakHashMap<MainActivity, LinearLayout>()
    private val dashboards = WeakHashMap<MainActivity, LinearLayout>()
    private val refreshRunnables = WeakHashMap<MainActivity, Runnable>()
    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                if (activity is MainActivity) install(activity)
            }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) {
                if (activity is MainActivity) refreshRunnables[activity]?.let(handler::removeCallbacks)
            }
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle?) = Unit
            override fun onActivityDestroyed(activity: Activity) {
                if (activity is MainActivity) {
                    refreshRunnables.remove(activity)?.let(handler::removeCallbacks)
                    installed.remove(activity)
                    wrappers.remove(activity)
                    dashboards.remove(activity)
                }
            }
        })
    }

    private fun install(activity: MainActivity) {
        if (installed[activity] == true) {
            scheduleRefresh(activity)
            return
        }
        installed[activity] = true
        val root = activity.window.decorView
        if (!root.viewTreeObserver.isAlive) return
        root.viewTreeObserver.addOnGlobalLayoutListener {
            val menu = findMenu(root) ?: return@addOnGlobalLayoutListener
            val wrapper = ensureWrapper(activity) ?: return@addOnGlobalLayoutListener
            if (menu.selectedItem?.toString() == "RINGKASAN") {
                ensureDashboard(activity, wrapper)
                refreshDashboardData(activity)
            } else {
                removeDashboard(activity, wrapper)
            }
        }
        scheduleRefresh(activity)
    }

    private fun scheduleRefresh(activity: MainActivity) {
        if (refreshRunnables[activity] != null) return
        val runnable = object : Runnable {
            override fun run() {
                refreshDashboardData(activity)
                if (installed[activity] == true) {
                    handler.postDelayed(this, 1_000L)
                }
            }
        }
        refreshRunnables[activity] = runnable
        handler.post(runnable)
    }

    private fun ensureWrapper(activity: MainActivity): LinearLayout? {
        wrappers[activity]?.let { return it }
        val content = content(activity) ?: return null
        var parent = content.parent
        var scroll: ScrollView? = null
        while (parent != null) {
            if (parent is ScrollView) { scroll = parent; break }
            parent = parent.parent
        }
        val host = scroll ?: return null
        val existing = host.getChildAt(0)
        if (existing is LinearLayout && existing.getTag(WRAPPER_TAG) == true) {
            wrappers[activity] = existing
            return existing
        }
        if (host.childCount != 1 || existing !== content) return null
        host.removeView(content)
        val wrapper = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setTag(WRAPPER_TAG, true)
            layoutParams = ViewGroup.LayoutParams(-1, -2)
        }
        wrapper.addView(content, LinearLayout.LayoutParams(-1, -2))
        host.addView(wrapper, ViewGroup.LayoutParams(-1, -2))
        wrappers[activity] = wrapper
        return wrapper
    }

    private fun ensureDashboard(activity: MainActivity, wrapper: LinearLayout) {
        if (dashboards[activity]?.parent === wrapper) return
        val existing = wrapper.findViewWithTag<View>(DASHBOARD_TAG)
        if (existing is LinearLayout) {
            dashboards[activity] = existing
            return
        }
        val intent = currentIntent(activity) ?: return
        val dashboard = buildDashboard(activity, intent)
        wrapper.addView(dashboard, LinearLayout.LayoutParams(-1, -2))
        dashboards[activity] = dashboard
    }

    private fun removeDashboard(activity: MainActivity, wrapper: LinearLayout) {
        val dashboard = dashboards.remove(activity) ?: wrapper.findViewWithTag<View>(DASHBOARD_TAG) as? LinearLayout ?: return
        wrapper.removeView(dashboard)
    }

    private fun buildDashboard(activity: MainActivity, intent: Intent): LinearLayout {
        val dashboard = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setTag(DASHBOARD_TAG, true)
        }
        addTitle(dashboard, "RINGKASAN · DASHBOARD TERPADU")
        dashboard.addView(card(activity, statusText(intent), 15f).apply { setTag(TAG_STATUS) }, params(4))
        dashboard.addView(card(activity, equityText(activity, intent), 14f).apply { setTag(TAG_EQUITY) }, params(6))
        addTitle(dashboard, "AI VS ACTUAL · SESI INI")
        dashboard.addView(buildAiTable(activity, intent), params(2))
        dashboard.addView(card(activity, "AI BUY/SELL/HOLD adalah keputusan. Actual hanya berasal dari ledger OPEN/CLOSE. HOLD actual = 0 karena HOLD bukan order.", 12f), params(5))
        addTitle(dashboard, "KONTROL SESI")
        val controls = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        controls.addView(actionButton(activity, "MULAI") { invokeStartDialog(activity) }, weight())
        controls.addView(actionButton(activity, "LANJUTKAN") { sendService(activity, MireiForegroundService.ACTION_START) }, weight())
        controls.addView(actionButton(activity, "TOP UP") { showTopUpDialog(activity) }, weight())
        dashboard.addView(controls, params(3))
        dashboard.addView(actionButton(activity, "JEDA / HOLD") { sendService(activity, MireiForegroundService.ACTION_HOLD) }, params(2))
        dashboard.addView(actionButton(activity, "BERHENTI") { sendService(activity, MireiForegroundService.ACTION_STOP) }, params(2))
        dashboard.addView(actionButton(activity, "TUTUP SEMUA POSISI") { sendService(activity, MireiForegroundService.ACTION_CLOSE_ALL) }, params(2))
        addTitle(dashboard, "EVENT / GATE TERAKHIR")
        dashboard.addView(card(activity, eventText(intent), 13f).apply { setTag(TAG_EVENT) }, params(5))
        addTitle(dashboard, "KEPUTUSAN TERAKHIR")
        dashboard.addView(card(activity, decisionText(intent), 13f).apply { setTag(TAG_DECISION) }, params(5))
        addTitle(dashboard, "KESEHATAN")
        dashboard.addView(card(activity, healthText(intent), 13f).apply { setTag(TAG_HEALTH) }, params(5))
        return dashboard
    }

    private fun buildAiTable(context: Context, intent: Intent): TableLayout {
        val table = TableLayout(context).apply { isStretchAllColumns = true; setTag(TAG_AI_TABLE) }
        table.addView(tableRow(context, listOf("SUMBER", "BUY", "HOLD", "SELL"), true))
        table.addView(tableRow(context, listOf("AI DECISION", "0", "0", "0"), false).apply { setTag(TAG_AI_ROW) })
        table.addView(tableRow(context, listOf("ACTUAL PAPER", "0", "0", "0"), false).apply { setTag(TAG_ACTUAL_ROW) })
        updateAiTable(context, table, intent)
        return table
    }

    private fun refreshDashboardData(activity: MainActivity) {
        val dashboard = dashboards[activity] ?: return
        val intent = currentIntent(activity) ?: return
        val menu = findMenu(activity.window.decorView)?.selectedItem?.toString()
        if (menu != "RINGKASAN") return
        (dashboard.findViewWithTag<View>(TAG_STATUS) as? TextView)?.text = statusText(intent)
        (dashboard.findViewWithTag<View>(TAG_EQUITY) as? TextView)?.text = equityText(activity, intent)
        (dashboard.findViewWithTag<View>(TAG_EVENT) as? TextView)?.text = eventText(intent)
        (dashboard.findViewWithTag<View>(TAG_DECISION) as? TextView)?.text = decisionText(intent)
        (dashboard.findViewWithTag<View>(TAG_HEALTH) as? TextView)?.text = healthText(intent)
        (dashboard.findViewWithTag<View>(TAG_AI_TABLE) as? TableLayout)?.let { updateAiTable(activity, it, intent) }
    }

    private fun updateAiTable(context: Context, table: TableLayout, intent: Intent) {
        val sessionStart = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(context)
        val trades = runCatching { db.recentTrades(200).filter { sessionStart == 0L || it.openedAtEpochMs >= sessionStart } }.getOrDefault(emptyList())
        val closed = trades.filter { it.closedAtEpochMs != null }
        val suggestions = runCatching { db.recentSuggestions(300).filter { sessionStart == 0L || it.createdAtEpochMs >= sessionStart } }.getOrDefault(emptyList())
        val aiBuy = suggestions.count { it.action == "BUY" }
        val aiHold = suggestions.count { it.action == "HOLD" }
        val aiSell = suggestions.count { it.action == "SELL" || it.action == "CLOSE" }
        val actualBuy = trades.count { it.side == "BUY" || it.side == "RE_ENTRY" || it.side == "INITIAL_HOLDING" }
        val actualSell = closed.size
        val aiRow = table.findViewWithTag<View>(TAG_AI_ROW) as? TableRow
        val actualRow = table.findViewWithTag<View>(TAG_ACTUAL_ROW) as? TableRow
        setRow(aiRow, listOf("AI DECISION", aiBuy.toString(), aiHold.toString(), aiSell.toString()))
        setRow(actualRow, listOf("ACTUAL PAPER", actualBuy.toString(), "0", actualSell.toString()))
    }

    private fun setRow(row: TableRow?, values: List<String>) {
        if (row == null) return
        values.forEachIndexed { index, value -> (row.getChildAt(index) as? TextView)?.text = value }
    }

    private fun equityText(activity: MainActivity, intent: Intent): String {
        val sessionStart = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching { db.recentTrades(200).filter { sessionStart == 0L || it.openedAtEpochMs >= sessionStart } }.getOrDefault(emptyList())
        val closed = trades.filter { it.closedAtEpochMs != null }
        val wins = closed.count { it.pnlIdr > 0.0 }
        val winRate = if (closed.isEmpty()) 0.0 else wins * 100.0 / closed.size
        return "EQUITY   Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\nKAS      Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\nPOSISI   ${intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}/3\nWIN RATE ${"%.2f".format(Locale.US, winRate)}%  (${wins}/${closed.size})\nMODAL    Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_TOTAL_CAPITAL, 0.0))}"
    }

    private fun eventText(i: Intent): String {
        val execution = i.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Belum ada OPEN/CLOSE pada tick terakhir." }
        val gates = i.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty().ifBlank { "Tidak ada gate yang tercatat." }.split("|").joinToString("\n") { "• ${it.trim().replace('_', ' ')}" }
        return "EVENT\n$execution\n\nGATE / BLOK RISIKO\n$gates"
    }

    private fun decisionText(i: Intent): String {
        val action = i.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val confidence = (i.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()
        val rationale = i.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty().replace('_', ' ').ifBlank { "belum ada alasan" }
        return "$action · $confidence%\n$rationale"
    }

    private fun healthText(i: Intent): String = "Internet: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)) "OK" else "PUTUS"}\nMarket: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}\nExchange: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)) "OK" else "TIDAK SIAP"}"

    private fun invokeStartDialog(activity: MainActivity) {
        runCatching { MainActivity::class.java.getDeclaredMethod("showStartDialog").apply { isAccessible = true }.invoke(activity) }
            .onFailure { AlertDialog.Builder(activity).setTitle("Mirei").setMessage("Form MULAI tidak dapat dibuka: ${it.message ?: "error"}").setPositiveButton("OK", null).show() }
    }

    private fun showTopUpDialog(activity: MainActivity) {
        val field = EditText(activity).apply { hint = "Nominal IDR"; inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true) }
        AlertDialog.Builder(activity).setTitle("TOP UP PAPER").setMessage("Tambahkan dana tanpa menghapus posisi yang sudah berjalan.").setView(field).setNegativeButton("BATAL", null).setPositiveButton("TOP UP") { _, _ ->
            val amount = field.text.toString().trim().replace(".", "").replace(",", ".").toDoubleOrNull() ?: 0.0
            if (amount > 0.0) sendService(activity, MireiForegroundService.ACTION_TOP_UP) { putExtra(MireiForegroundService.EXTRA_TOP_UP_AMOUNT, amount) }
            else Toast.makeText(activity, "Nominal top up harus > 0", Toast.LENGTH_SHORT).show()
        }.show()
    }

    private fun sendService(activity: MainActivity, action: String, extras: Intent.() -> Unit = {}) {
        val intent = Intent(activity, MireiForegroundService::class.java).apply { this.action = action; extras() }
        runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) }
            .onFailure { AlertDialog.Builder(activity).setTitle("Mirei").setMessage("Perintah tidak dapat dijalankan: ${it.message ?: "error"}").setPositiveButton("OK", null).show() }
    }

    private fun currentIntent(activity: MainActivity): Intent? = runCatching { MainActivity::class.java.getDeclaredField("currentIntent").apply { isAccessible = true }.get(activity) as? Intent }.getOrNull()
    private fun content(activity: MainActivity): LinearLayout? = runCatching { MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(activity) as LinearLayout }.getOrNull()

    private fun findMenu(view: View): Spinner? {
        if (view is Spinner && view.selectedItem?.toString() in MENU_LABELS) return view
        if (view !is ViewGroup) return null
        for (i in 0 until view.childCount) findMenu(view.getChildAt(i))?.let { return it }
        return null
    }

    private fun statusText(i: Intent): String = when (i.getStringExtra(MireiForegroundService.EXTRA_STATE)) {
        "RUNNING" -> "🟢 RUNNING · PAPER ONLY"
        "HOLD" -> "🟡 HOLD / JEDA · PAPER ONLY"
        "CLOSE_ALL" -> "⚪ CLOSE ALL"
        "ERROR" -> "🔴 DAMAGE"
        else -> "🟡 STOPPED · PAPER ONLY"
    }

    private fun addTitle(parent: LinearLayout, value: String) {
        parent.addView(TextView(parent.context).apply { text = value; textSize = 20f; setTextColor(Color.WHITE); setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(6, 8, 6, 6) }, params(2))
    }
    private fun card(context: Context, value: String, size: Float) = TextView(context).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(10, 10, 10, 10); setBackgroundColor(Color.rgb(24, 34, 43)) }
    private fun actionButton(context: Context, label: String, click: () -> Unit) = Button(context).apply { text = label; minHeight = 50; setOnClickListener { click() } }
    private fun tableRow(context: Context, values: List<String>, header: Boolean) = TableRow(context).apply { values.forEach { value -> addView(TextView(context).apply { text = value; textSize = 11f; setTextColor(if (header) Color.LTGRAY else Color.WHITE); setPadding(6, 7, 6, 7); minWidth = 70; if (header) setTypeface(typeface, android.graphics.Typeface.BOLD) }) } }
    private fun params(top: Int = 0) = LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top; bottomMargin = 4 }
    private fun weight() = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 4 }
    private fun money(value: Double) = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)
    companion object {
        private val DASHBOARD_TAG = Any()
        private val WRAPPER_TAG = Any()
        private const val TAG_STATUS = "mirei_dash_status"
        private const val TAG_EQUITY = "mirei_dash_equity"
        private const val TAG_AI_TABLE = "mirei_dash_ai_table"
        private const val TAG_AI_ROW = "mirei_dash_ai_row"
        private const val TAG_ACTUAL_ROW = "mirei_dash_actual_row"
        private const val TAG_EVENT = "mirei_dash_event"
        private const val TAG_DECISION = "mirei_dash_decision"
        private const val TAG_HEALTH = "mirei_dash_health"
        private val MENU_LABELS = setOf("RINGKASAN", "PASAR", "POSISI", "AKTIVITAS", "KEPUTUSAN", "RISIKO", "EXCHANGE / API", "PENGATURAN", "LOG / AUDIT")
    }
}
