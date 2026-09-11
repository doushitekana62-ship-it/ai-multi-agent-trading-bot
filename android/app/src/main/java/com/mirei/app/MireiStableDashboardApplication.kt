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

/** Stable dashboard host: MainActivity content and dashboard are siblings, never competing. */
class MireiStableDashboardApplication : Application() {
    private val installed = WeakHashMap<MainActivity, Boolean>()
    private val wrappers = WeakHashMap<MainActivity, LinearLayout>()
    private val dashboards = WeakHashMap<MainActivity, LinearLayout>()
    private val refreshers = WeakHashMap<MainActivity, Runnable>()
    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) { if (activity is MainActivity) install(activity) }
            override fun onActivityCreated(activity: Activity, state: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) { if (activity is MainActivity) refreshers[activity]?.let(handler::removeCallbacks) }
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle?) = Unit
            override fun onActivityDestroyed(activity: Activity) {
                if (activity is MainActivity) {
                    refreshers.remove(activity)?.let(handler::removeCallbacks)
                    installed.remove(activity); wrappers.remove(activity); dashboards.remove(activity)
                }
            }
        })
    }

    private fun install(activity: MainActivity) {
        if (installed.put(activity, true) == true) { scheduleRefresh(activity); return }
        val root = activity.window.decorView
        if (!root.viewTreeObserver.isAlive) return
        root.viewTreeObserver.addOnGlobalLayoutListener {
            val menu = findMenu(root) ?: return@addOnGlobalLayoutListener
            val wrapper = ensureWrapper(activity) ?: return@addOnGlobalLayoutListener
            if (menu.selectedItem?.toString() == "RINGKASAN") {
                ensureDashboard(activity, wrapper)
                refreshDashboard(activity)
            } else removeDashboard(activity, wrapper)
        }
        scheduleRefresh(activity)
    }

    private fun scheduleRefresh(activity: MainActivity) {
        if (refreshers.containsKey(activity)) return
        val r = object : Runnable {
            override fun run() {
                refreshDashboard(activity)
                if (installed[activity] == true) handler.postDelayed(this, 1000L)
            }
        }
        refreshers[activity] = r
        handler.post(r)
    }

    private fun ensureWrapper(activity: MainActivity): LinearLayout? {
        wrappers[activity]?.let { return it }
        val content = content(activity) ?: return null
        var p = content.parent
        var scroll: ScrollView? = null
        while (p != null) { if (p is ScrollView) { scroll = p; break }; p = p.parent }
        val host = scroll ?: return null
        val child = host.getChildAt(0)
        if (child is LinearLayout && child.getTag() == WRAPPER_TAG) { wrappers[activity] = child; return child }
        if (host.childCount != 1 || child !== content) return null
        host.removeView(content)
        val wrapper = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setTag(WRAPPER_TAG) }
        wrapper.addView(content, LinearLayout.LayoutParams(-1, -2))
        host.addView(wrapper, ViewGroup.LayoutParams(-1, -2))
        wrappers[activity] = wrapper
        return wrapper
    }

    private fun ensureDashboard(activity: MainActivity, wrapper: LinearLayout) {
        if (dashboards[activity]?.parent === wrapper) return
        (wrapper.findViewWithTag<View>(DASHBOARD_TAG) as? LinearLayout)?.let { dashboards[activity] = it; return }
        val intent = currentIntent(activity) ?: return
        val dashboard = buildDashboard(activity, intent)
        wrapper.addView(dashboard, LinearLayout.LayoutParams(-1, -2))
        dashboards[activity] = dashboard
    }

    private fun removeDashboard(activity: MainActivity, wrapper: LinearLayout) {
        val d = dashboards.remove(activity) ?: wrapper.findViewWithTag<View>(DASHBOARD_TAG) as? LinearLayout ?: return
        wrapper.removeView(d)
    }

    private fun buildDashboard(a: MainActivity, i: Intent) = LinearLayout(a).apply {
        orientation = LinearLayout.VERTICAL; setTag(DASHBOARD_TAG)
        addTitle(this, "RINGKASAN · DASHBOARD TERPADU")
        addView(card(a, statusText(i), 15f).apply { setTag(TAG_STATUS) }, params(4))
        addView(card(a, equityText(a, i), 14f).apply { setTag(TAG_EQUITY) }, params(6))
        addTitle(this, "AI VS ACTUAL · SESI INI")
        addView(buildAiTable(a, i), params(2))
        addView(card(a, "AI BUY/SELL/HOLD adalah keputusan. Actual hanya berasal dari ledger OPEN/CLOSE. HOLD actual = 0 karena HOLD bukan order.", 12f), params(5))
        addTitle(this, "KONTROL SESI")
        val controls = LinearLayout(a).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
        controls.addView(action(a, "MULAI") { invokeStartDialog(a) }, weight())
        controls.addView(action(a, "LANJUTKAN") { send(a, MireiForegroundService.ACTION_START) }, weight())
        controls.addView(action(a, "TOP UP") { topUp(a) }, weight())
        addView(controls, params(3))
        addView(action(a, "JEDA / HOLD") { send(a, MireiForegroundService.ACTION_HOLD) }, params(2))
        addView(action(a, "BERHENTI") { send(a, MireiForegroundService.ACTION_STOP) }, params(2))
        addView(action(a, "TUTUP SEMUA POSISI") { send(a, MireiForegroundService.ACTION_CLOSE_ALL) }, params(2))
        addTitle(this, "EVENT / GATE TERAKHIR")
        addView(card(a, eventText(i), 13f).apply { setTag(TAG_EVENT) }, params(5))
        addTitle(this, "KEPUTUSAN TERAKHIR")
        addView(card(a, decisionText(i), 13f).apply { setTag(TAG_DECISION) }, params(5))
        addTitle(this, "KESEHATAN")
        addView(card(a, healthText(i), 13f).apply { setTag(TAG_HEALTH) }, params(5))
    }

    private fun buildAiTable(c: Context, i: Intent) = TableLayout(c).apply {
        isStretchAllColumns = true; setTag(TAG_AI)
        addView(row(c, listOf("SUMBER", "BUY", "HOLD", "SELL"), true))
        addView(row(c, listOf("AI DECISION", "0", "0", "0"), false).apply { setTag(TAG_AI_ROW) })
        addView(row(c, listOf("ACTUAL PAPER", "0", "0", "0"), false).apply { setTag(TAG_ACTUAL_ROW) })
        updateAi(this, i)
    }

    private fun refreshDashboard(a: MainActivity) {
        val d = dashboards[a] ?: return
        if (findMenu(a.window.decorView)?.selectedItem?.toString() != "RINGKASAN") return
        val i = currentIntent(a) ?: return
        (d.findViewWithTag<View>(TAG_STATUS) as? TextView)?.text = statusText(i)
        (d.findViewWithTag<View>(TAG_EQUITY) as? TextView)?.text = equityText(a, i)
        (d.findViewWithTag<View>(TAG_EVENT) as? TextView)?.text = eventText(i)
        (d.findViewWithTag<View>(TAG_DECISION) as? TextView)?.text = decisionText(i)
        (d.findViewWithTag<View>(TAG_HEALTH) as? TextView)?.text = healthText(i)
        (d.findViewWithTag<View>(TAG_AI) as? TableLayout)?.let { updateAi(it, i) }
    }

    private fun updateAi(table: TableLayout, i: Intent) {
        val start = i.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(table.context)
        val trades = runCatching { db.recentTrades(200).filter { start == 0L || it.openedAtEpochMs >= start } }.getOrDefault(emptyList())
        val closed = trades.count { it.closedAtEpochMs != null }
        val suggestions = runCatching { db.recentSuggestions(300).filter { start == 0L || it.createdAtEpochMs >= start } }.getOrDefault(emptyList())
        setRow(table.findViewWithTag(TAG_AI_ROW) as? TableRow, listOf("AI DECISION", suggestions.count { it.action == "BUY" }.toString(), suggestions.count { it.action == "HOLD" }.toString(), suggestions.count { it.action == "SELL" || it.action == "CLOSE" }.toString()))
        setRow(table.findViewWithTag(TAG_ACTUAL_ROW) as? TableRow, listOf("ACTUAL PAPER", trades.count { it.side == "BUY" || it.side == "RE_ENTRY" || it.side == "INITIAL_HOLDING" }.toString(), "0", closed.toString()))
    }

    private fun setRow(row: TableRow?, values: List<String>) { if (row != null) values.forEachIndexed { n, v -> (row.getChildAt(n) as? TextView)?.text = v } }

    private fun equityText(a: MainActivity, i: Intent): String {
        val start = i.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val closed = runCatching { MireiDatabase(a).recentTrades(200).filter { start == 0L || it.openedAtEpochMs >= start }.filter { it.closedAtEpochMs != null } }.getOrDefault(emptyList())
        val wins = closed.count { it.pnlIdr > 0.0 }
        val rate = if (closed.isEmpty()) 0.0 else wins * 100.0 / closed.size
        return "EQUITY   Rp ${money(i.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\nKAS      Rp ${money(i.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\nPOSISI   ${i.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}/3\nWIN RATE ${"%.2f".format(Locale.US, rate)}%  ($wins/${closed.size})\nMODAL    Rp ${money(i.getDoubleExtra(MireiForegroundService.EXTRA_TOTAL_CAPITAL, 0.0))}"
    }

    private fun eventText(i: Intent): String { val e = i.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Belum ada OPEN/CLOSE pada tick terakhir." }; val g = i.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty().ifBlank { "Tidak ada gate yang tercatat." }.split("|").joinToString("\n") { "• ${it.trim().replace('_', ' ')}" }; return "EVENT\n$e\n\nGATE / BLOK RISIKO\n$g" }
    private fun decisionText(i: Intent): String { val a = i.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"; val c = (i.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt(); val r = i.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty().replace('_', ' ').ifBlank { "belum ada alasan" }; return "$a · $c%\n$r" }
    private fun healthText(i: Intent) = "Internet: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)) "OK" else "PUTUS"}\nMarket: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}\nExchange: ${if (i.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)) "OK" else "TIDAK SIAP"}"
    private fun statusText(i: Intent) = when (i.getStringExtra(MireiForegroundService.EXTRA_STATE)) { "RUNNING" -> "🟢 RUNNING · PAPER ONLY"; "HOLD" -> "🟡 HOLD / JEDA · PAPER ONLY"; "CLOSE_ALL" -> "⚪ CLOSE ALL"; "ERROR" -> "🔴 DAMAGE"; else -> "🟡 STOPPED · PAPER ONLY" }

    private fun invokeStartDialog(a: MainActivity) { runCatching { MainActivity::class.java.getDeclaredMethod("showStartDialog").apply { isAccessible = true }.invoke(a) }.onFailure { AlertDialog.Builder(a).setTitle("Mirei").setMessage("Form MULAI tidak dapat dibuka: ${it.message ?: "error"}").setPositiveButton("OK", null).show() } }
    private fun topUp(a: MainActivity) {
        val f = EditText(a).apply { hint = "Nominal IDR"; inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true) }
        AlertDialog.Builder(a).setTitle("TOP UP PAPER").setMessage("Tambahkan dana tanpa menghapus posisi yang sudah berjalan.").setView(f).setNegativeButton("BATAL", null).setPositiveButton("TOP UP") { _, _ -> val v = f.text.toString().trim().replace(".", "").replace(",", ".").toDoubleOrNull() ?: 0.0; if (v > 0.0) send(a, MireiForegroundService.ACTION_TOP_UP) { putExtra(MireiForegroundService.EXTRA_TOP_UP_AMOUNT, v) } else Toast.makeText(a, "Nominal top up harus > 0", Toast.LENGTH_SHORT).show() }.show()
    }
    private fun send(a: MainActivity, action: String, extras: Intent.() -> Unit = {}) { val i = Intent(a, MireiForegroundService::class.java).apply { this.action = action; extras() }; runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) a.startForegroundService(i) else a.startService(i) }.onFailure { AlertDialog.Builder(a).setTitle("Mirei").setMessage("Perintah tidak dapat dijalankan: ${it.message ?: "error"}").setPositiveButton("OK", null).show() } }
    private fun currentIntent(a: MainActivity): Intent? = runCatching { MainActivity::class.java.getDeclaredField("currentIntent").apply { isAccessible = true }.get(a) as? Intent }.getOrNull()
    private fun content(a: MainActivity): LinearLayout? = runCatching { MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(a) as LinearLayout }.getOrNull()
    private fun findMenu(v: View): Spinner? { if (v is Spinner && v.selectedItem?.toString() in MENU_LABELS) return v; if (v !is ViewGroup) return null; for (n in 0 until v.childCount) findMenu(v.getChildAt(n))?.let { return it }; return null }
    private fun addTitle(p: LinearLayout, s: String) { p.addView(TextView(p.context).apply { text = s; textSize = 20f; setTextColor(Color.WHITE); setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(6, 8, 6, 6) }, params(2)) }
    private fun card(c: Context, s: String, z: Float) = TextView(c).apply { text = s; textSize = z; setTextColor(Color.WHITE); setPadding(10, 10, 10, 10); setBackgroundColor(Color.rgb(24, 34, 43)) }
    private fun action(c: Context, s: String, f: () -> Unit) = Button(c).apply { text = s; minHeight = 50; setOnClickListener { f() } }
    private fun row(c: Context, values: List<String>, header: Boolean) = TableRow(c).apply { values.forEach { value -> addView(TextView(c).apply { text = value; textSize = 11f; setTextColor(if (header) Color.LTGRAY else Color.WHITE); setPadding(6, 7, 6, 7); minWidth = 70; if (header) setTypeface(typeface, android.graphics.Typeface.BOLD) }) } }
    private fun params(t: Int = 0) = LinearLayout.LayoutParams(-1, -2).apply { topMargin = t; bottomMargin = 4 }
    private fun weight() = LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = 4 }
    private fun money(v: Double) = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(v)

    companion object {
        private const val WRAPPER_TAG = "mirei_dashboard_wrapper"
        private const val DASHBOARD_TAG = "mirei_stable_dashboard"
        private const val TAG_STATUS = "mirei_dash_status"
        private const val TAG_EQUITY = "mirei_dash_equity"
        private const val TAG_AI = "mirei_dash_ai"
        private const val TAG_AI_ROW = "mirei_dash_ai_row"
        private const val TAG_ACTUAL_ROW = "mirei_dash_actual_row"
        private const val TAG_EVENT = "mirei_dash_event"
        private const val TAG_DECISION = "mirei_dash_decision"
        private const val TAG_HEALTH = "mirei_dash_health"
        private val MENU_LABELS = setOf("RINGKASAN", "PASAR", "POSISI", "AKTIVITAS", "KEPUTUSAN", "RISIKO", "EXCHANGE / API", "PENGATURAN", "LOG / AUDIT")
    }
}
