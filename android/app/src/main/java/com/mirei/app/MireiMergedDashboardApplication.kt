package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.app.Application
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
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
 * Merges the enhanced dashboard with MainActivity's original summary.
 * MainActivity remains the renderer owner: this class only inserts one dashboard
 * section into the existing RINGKASAN content and never clears/rebuilds content.
 */
class MireiMergedDashboardApplication : Application() {
    private val installed = WeakHashMap<MainActivity, Boolean>()
    private val lastTick = WeakHashMap<MainActivity, Long>()

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                if (activity is MainActivity) install(activity)
            }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) { if (activity is MainActivity) lastTick.remove(activity) }
        })
    }

    private fun install(activity: MainActivity) {
        if (installed[activity] == true) return
        installed[activity] = true
        val root = activity.window.decorView
        if (!root.viewTreeObserver.isAlive) return
        root.viewTreeObserver.addOnGlobalLayoutListener {
            val menu = findMenu(root) ?: return@addOnGlobalLayoutListener
            if (menu.selectedItem?.toString() != "RINGKASAN") return@addOnGlobalLayoutListener
            val intent = currentIntent(activity) ?: return@addOnGlobalLayoutListener
            val tick = intent.getLongExtra(MireiForegroundService.EXTRA_TICK, 0L)
            val content = content(activity) ?: return@addOnGlobalLayoutListener
            if (hasDashboard(content)) return@addOnGlobalLayoutListener
            if (tick > 0L && lastTick[activity] == tick) return@addOnGlobalLayoutListener
            lastTick[activity] = tick
            root.post { mergeDashboard(activity) }
        }
    }

    private fun mergeDashboard(activity: MainActivity) {
        val content = content(activity) ?: return
        if (hasDashboard(content)) return
        val intent = currentIntent(activity) ?: return
        val dashboard = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setTag(DASHBOARD_TAG)
        }
        addTitle(dashboard, "RINGKASAN · DASHBOARD TERPADU")
        dashboard.addView(card(activity, statusText(intent), 15f), params(4))

        val sessionStart = intent.getLongExtra(MireiForegroundService.EXTRA_SESSION_CREATED, 0L)
        val db = MireiDatabase(activity)
        val trades = runCatching {
            db.recentTrades(200).filter { sessionStart == 0L || it.openedAtEpochMs >= sessionStart }
        }.getOrDefault(emptyList())
        val closed = trades.filter { it.closedAtEpochMs != null }
        val wins = closed.count { it.pnlIdr > 0.0 }
        val winRate = if (closed.isEmpty()) 0.0 else wins * 100.0 / closed.size
        val suggestions = runCatching {
            db.recentSuggestions(300).filter { sessionStart == 0L || it.createdAtEpochMs >= sessionStart }
        }.getOrDefault(emptyList())
        val aiBuy = suggestions.count { it.action == "BUY" }
        val aiHold = suggestions.count { it.action == "HOLD" }
        val aiSell = suggestions.count { it.action == "SELL" || it.action == "CLOSE" }
        val actualBuy = trades.count { it.side == "BUY" || it.side == "RE_ENTRY" || it.side == "INITIAL_HOLDING" }
        val actualSell = closed.size

        dashboard.addView(card(activity,
            "EQUITY   Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0))}\n" +
                "KAS      Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0))}\n" +
                "POSISI   ${intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)}/3\n" +
                "WIN RATE ${"%.2f".format(Locale.US, winRate)}%  (${wins}/${closed.size})\n" +
                "MODAL    Rp ${money(intent.getDoubleExtra(MireiForegroundService.EXTRA_TOTAL_CAPITAL, 0.0))}", 14f), params(6))

        addTitle(dashboard, "AI VS ACTUAL · SESI INI")
        val table = TableLayout(activity).apply { isStretchAllColumns = true }
        table.addView(tableRow(activity, listOf("SUMBER", "BUY", "HOLD", "SELL"), true))
        table.addView(tableRow(activity, listOf("AI DECISION", aiBuy.toString(), aiHold.toString(), aiSell.toString()), false))
        table.addView(tableRow(activity, listOf("ACTUAL PAPER", actualBuy.toString(), "0", actualSell.toString()), false))
        dashboard.addView(table, params(2))
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
        val execution = intent.getStringExtra(MireiForegroundService.EXTRA_RECENT_EXECUTIONS).orEmpty().ifBlank { "Belum ada OPEN/CLOSE pada tick terakhir." }
        val gates = intent.getStringExtra(MireiForegroundService.EXTRA_ENTRY_REASONS).orEmpty().ifBlank { "Tidak ada gate yang tercatat." }.split("|").joinToString("\n") { "• ${it.trim().replace('_', ' ')}" }
        dashboard.addView(card(activity, "EVENT\n$execution\n\nGATE / BLOK RISIKO\n$gates", 13f), params(5))

        addTitle(dashboard, "KEPUTUSAN TERAKHIR")
        val action = intent.getStringExtra(MireiForegroundService.EXTRA_ACTION) ?: "HOLD"
        val confidence = (intent.getDoubleExtra(MireiForegroundService.EXTRA_CONFIDENCE, 0.0) * 100).toInt()
        val rationale = intent.getStringExtra(MireiForegroundService.EXTRA_RATIONALE).orEmpty().replace('_', ' ').ifBlank { "belum ada alasan" }
        dashboard.addView(card(activity, "$action · $confidence%\n$rationale", 13f), params(5))

        addTitle(dashboard, "KESEHATAN")
        dashboard.addView(card(activity,
            "Internet: ${if (intent.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)) "OK" else "PUTUS"}\n" +
                "Market: ${if (intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)) "SEGAR" else "STALE"}\n" +
                "Exchange: ${if (intent.getBooleanExtra(MireiForegroundService.EXTRA_EXCHANGE_HEALTHY, false)) "OK" else "TIDAK SIAP"}", 13f), params(5))

        val insertAt = minOf(2, content.childCount)
        content.addView(dashboard, insertAt)
    }

    private fun hasDashboard(content: LinearLayout): Boolean {
        return content.findViewWithTag<View>(DASHBOARD_TAG) != null
    }

    private fun invokeStartDialog(activity: MainActivity) {
        runCatching {
            MainActivity::class.java.getDeclaredMethod("showStartDialog").apply { isAccessible = true }.invoke(activity)
        }.onFailure {
            AlertDialog.Builder(activity).setTitle("Mirei").setMessage("Form MULAI tidak dapat dibuka: ${it.message ?: "error"}").setPositiveButton("OK", null).show()
        }
    }

    private fun showTopUpDialog(activity: MainActivity) {
        val field = EditText(activity).apply {
            hint = "Nominal IDR"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
        }
        AlertDialog.Builder(activity)
            .setTitle("TOP UP PAPER")
            .setMessage("Tambahkan dana tanpa menghapus posisi yang sudah berjalan.")
            .setView(field)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("TOP UP") { _, _ ->
                val raw = field.text.toString().trim().replace(".", "").replace(",", ".")
                val amount = raw.toDoubleOrNull() ?: 0.0
                if (amount > 0.0) sendService(activity, MireiForegroundService.ACTION_TOP_UP) {
                    putExtra(MireiForegroundService.EXTRA_TOP_UP_AMOUNT, amount)
                } else Toast.makeText(activity, "Nominal top up harus > 0", Toast.LENGTH_SHORT).show()
            }.show()
    }

    private fun sendService(activity: MainActivity, action: String, extras: Intent.() -> Unit = {}) {
        val intent = Intent(activity, MireiForegroundService::class.java).apply { this.action = action; extras() }
        runCatching {
            if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent)
        }.onFailure {
            AlertDialog.Builder(activity).setTitle("Mirei").setMessage("Perintah tidak dapat dijalankan: ${it.message ?: "error"}").setPositiveButton("OK", null).show()
        }
    }

    private fun currentIntent(activity: MainActivity): Intent? = runCatching {
        MainActivity::class.java.getDeclaredField("currentIntent").apply { isAccessible = true }.get(activity) as? Intent
    }.getOrNull()

    private fun content(activity: MainActivity): LinearLayout? = runCatching {
        MainActivity::class.java.getDeclaredField("content").apply { isAccessible = true }.get(activity) as LinearLayout
    }.getOrNull()

    private fun findMenu(view: View): Spinner? {
        if (view is Spinner) {
            val value = view.selectedItem?.toString().orEmpty()
            if (value in setOf("RINGKASAN", "PASAR", "POSISI", "AKTIVITAS", "KEPUTUSAN", "RISIKO", "EXCHANGE / API", "PENGATURAN", "LOG / AUDIT")) return view
        }
        if (view !is ViewGroup) return null
        for (i in 0 until view.childCount) findMenu(view.getChildAt(i))?.let { return it }
        return null
    }

    private fun statusText(i: Intent): String {
        val state = when (i.getStringExtra(MireiForegroundService.EXTRA_STATE)) {
            "RUNNING" -> "🟢 RUNNING"
            "HOLD" -> "🟡 HOLD / JEDA"
            "CLOSE_ALL" -> "⚪ CLOSE ALL"
            "ERROR" -> "🔴 DAMAGE"
            else -> "🟡 STOPPED"
        }
        val internet = i.getBooleanExtra(MireiForegroundService.EXTRA_INTERNET, false)
        return "$state · ${if (internet) "MARKET CONNECTED" else "SEARCHING CONNECTION"} · PAPER ONLY"
    }

    private fun addTitle(parent: LinearLayout, value: String) {
        parent.addView(TextView(parent.context).apply {
            text = value; textSize = 20f; setTextColor(Color.WHITE); setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding(6, 8, 6, 6)
        }, params(2))
    }

    private fun card(context: Context, value: String, size: Float) = TextView(context).apply {
        text = value; textSize = size; setTextColor(Color.WHITE); setPadding(10, 10, 10, 10); setBackgroundColor(Color.rgb(24, 34, 43))
    }

    private fun actionButton(context: Context, label: String, click: () -> Unit) = Button(context).apply {
        text = label; minHeight = 50; setOnClickListener { click() }
    }

    private fun tableRow(context: Context, values: List<String>, header: Boolean) = TableRow(context).apply {
        values.forEach { value ->
            addView(TextView(context).apply {
                text = value; textSize = 11f; setTextColor(if (header) Color.LTGRAY else Color.WHITE); setPadding(6, 7, 6, 7); minWidth = 70
                if (header) setTypeface(typeface, android.graphics.Typeface.BOLD)
            })
        }
    }

    private fun params(top: Int = 0) = LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top; bottomMargin = 4 }
    private fun weight() = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 4 }
    private fun money(value: Double) = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }.format(value)

    companion object { private val DASHBOARD_TAG = Any() }
}
