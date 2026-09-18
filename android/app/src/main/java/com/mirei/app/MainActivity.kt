package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import com.mirei.app.core.PositionTradeConfigStore
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var content: LinearLayout
    private lateinit var status: TextView
    private val number = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 0 }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == MireiForegroundService.ACTION_STATUS) render(intent)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        PositionTradeConfigStore.reload(this)
        buildDashboard()
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(MireiForegroundService.ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(receiver, filter, RECEIVER_NOT_EXPORTED) else registerReceiver(receiver, filter)
        requestStatus()
    }

    override fun onStop() {
        runCatching { unregisterReceiver(receiver) }
        super.onStop()
    }

    private fun buildDashboard() {
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(12, 12, 12, 16)
            setBackgroundColor(Color.rgb(40, 40, 40))
        }
        shell.addView(text("MIREI", 28f, true))
        shell.addView(text("Paper trading · satu dashboard · SL/TP manual", 13f))
        status = card("STOP")
        shell.addView(status, margin(0, 8, 0, 8))

        val controls = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row1.addView(button("ATUR SL/TP") { showRiskDialog() }, gridParams())
        row1.addView(button("MULAI") { if (isRiskConfigured()) { status.text = "STATUS: LOADING · MIREI MENYIAPKAN..."; MireiStartSessionDialog.show(this@MainActivity) } else showRiskRequired() }, gridParams())
        row1.addView(button("STOP") { showStopDialog() }, gridParams())
        row2.addView(button("LANJUTKAN") { send(MireiForegroundService.ACTION_START) }, gridParams())
        row2.addView(button("TUTUP SEMUA") { send(MireiForegroundService.ACTION_CLOSE_ALL) }, gridParams())
        row2.addView(button("RESET") { confirmReset() }, gridParams())
        controls.addView(row1)
        controls.addView(row2)
        shell.addView(controls)

        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 10, 0, 0) }
        val scroll = ScrollView(this).apply { isFillViewport = true; addView(content, ViewGroup.LayoutParams(-1, -2)) }
        shell.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(shell)
    }

    private fun render(intent: Intent) {
        val state = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP"
        val balance = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val pnl = intent.getDoubleExtra(MireiForegroundService.EXTRA_PNL, 0.0)
        val positions = intent.getIntExtra(MireiForegroundService.EXTRA_POSITIONS, 0)
        val error = intent.getStringExtra(MireiForegroundService.EXTRA_ERROR).orEmpty()
        val lastTick = intent.getLongExtra(MireiForegroundService.EXTRA_LAST_TICK, 0L)
        val tickAgeSec = if (lastTick > 0L) ((System.currentTimeMillis() - lastTick).coerceAtLeast(0L) / 1000L) else -1L
        val heartbeat = when {
            state == "RUNNING" && tickAgeSec in 0..15 -> "AKTIF · TICK " + tickAgeSec + "d lalu"
            state == "RUNNING" -> "RUNNING · TICK TERLAMBAT " + tickAgeSec + "d"
            else -> state
        }

        val equityLines = positionRows.mapIndexed { index, row -> val p = row.split("|"); "${index + 1}. ${p.getOrNull(0) ?: "-"}  Rp ${number.format(p.getOrNull(8)?.toDoubleOrNull() ?: 0.0)}" }
        val pnlLines = positionRows.mapIndexed { index, row -> val p = row.split("|"); "${index + 1}. ${p.getOrNull(0) ?: "-"}  Rp ${number.format(p.getOrNull(5)?.toDoubleOrNull() ?: 0.0)}" }
        val positionLines = positionRows.mapIndexed { index, row -> val p = row.split("|"); "${index + 1}. ${p.getOrNull(0) ?: "-"}  Rp ${number.format(p.getOrNull(1)?.toDoubleOrNull() ?: 0.0)}" }
        status.text = "Status : " + heartbeat +
            "\nKas : Rp " + number.format(balance) +
            "\nEquity :" + if (equityLines.isEmpty()) " -" else "\n" + equityLines.joinToString("\n") +
            "\nPnl :" + if (pnlLines.isEmpty()) " -" else "\n" + pnlLines.joinToString("\n") +
            "\nPosisi : " + positions + "/10" +
            if (positionLines.isNotEmpty()) "\n" + positionLines.joinToString("\n") else "" +
            if (error.isNotBlank()) "\nERROR: " + error else ""

        content.removeAllViews()
        addSection("POSISI AKTIF")
        val rows = intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty().lines().filter { it.isNotBlank() }
        if (rows.isEmpty()) {
            content.addView(card("Tidak ada posisi aktif."))
        } else {
            rows.forEach { row ->
                val p = row.split('|')
                if (p.size >= 5) {
                    val unrealizedPnl = p.getOrNull(5)?.toDoubleOrNull() ?: 0.0
                    val mark = p.getOrNull(6)?.toDoubleOrNull() ?: 0.0
                    val cycleState = p.getOrNull(7) ?: "HOLDING"
                    val decision = p.getOrNull(8) ?: "HOLD"
                    val value = p[0] + " · " + cycleState + " · " + decision +
                        "\nMODAL: Rp " + number.format(p[1].toDoubleOrNull() ?: 0.0) +
                        "\nENTRY: Rp " + number.format(p[2].toDoubleOrNull() ?: 0.0) +
                        "\nHARGA SEKARANG: Rp " + number.format(mark) +
                        "\nSL: " + (if ((p[3].toDoubleOrNull() ?: 0.0) > 0.0) "Rp " + number.format(p[3].toDoubleOrNull() ?: 0.0) else "NONAKTIF") +
                        "\nTP: Rp " + number.format(p[4].toDoubleOrNull() ?: 0.0) +
                        "\nPnL BERJALAN: Rp " + number.format(unrealizedPnl)
                    content.addView(card(value, 13f))
                }
            }
        }

        addSection("HISTORY")
        renderHistoryTable()
    }

    private fun renderHistoryTable() {
        val rows = MireiDatabase(this).recentTrades(100)
        val table = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        table.addView(tableRow(listOf("WAKTU", "SYMBOL", "SIDE", "STATUS", "ENTRY", "EXIT", "PnL", "ALASAN"), true))
        rows.forEach { row ->
            table.addView(tableRow(listOf(
                formatTime(row.closedAtEpochMs ?: row.openedAtEpochMs),
                row.symbol,
                row.side,
                row.status,
                row.entryPrice?.let { number.format(it) } ?: "-",
                row.exitPrice?.let { number.format(it) } ?: "-",
                number.format(row.pnlIdr),
                row.exitReason ?: row.entryReason,
            ), false))
        }
        if (rows.isEmpty()) table.addView(text("Belum ada history.", 12f))
        content.addView(HorizontalScrollView(this).apply { addView(table) })
    }

    private fun showRiskDialog() {
        val current = PositionTradeConfigStore.snapshot()["*"]
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 4, 12, 4) }
        val sl = EditText(this).apply { hint = "SL %"; setSingleLine(true); setText((current?.stopLossPercent ?: 0.50).toString()) }
        val tp = EditText(this).apply { hint = "Target TP bersih Rp"; setSingleLine(true); setText((current?.manualNetProfitTargetIdr ?: 30.0).toString()) }
        val basis = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        val entry = RadioButton(this).apply { id = View.generateViewId(); text = "Harga ENTRY" }
        val initial = RadioButton(this).apply { id = View.generateViewId(); text = "MODAL BELI PERTAMA" }
        basis.addView(entry)
        basis.addView(initial)
        basis.check(if (current?.riskReferenceMode == RiskReferenceMode.INITIAL_CAPITAL) initial.id else entry.id)
        box.addView(text("SL dan TP manual berlaku untuk semua instrument yang belum memiliki profil khusus.", 12f))
        box.addView(sl)
        box.addView(tp)
        box.addView(basis)

        AlertDialog.Builder(this)
            .setTitle("ATUR SL/TP")
            .setView(box)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("SIMPAN") { _, _ ->
                val slValue = sl.text.toString().toDoubleOrNull()
                val tpValue = tp.text.toString().toDoubleOrNull()
                if (slValue == null || slValue < 0.0 || tpValue == null || tpValue <= 0.0) return@setPositiveButton
                val ref = if (basis.checkedRadioButtonId == initial.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                getSharedPreferences("mirei_settings", MODE_PRIVATE).edit()
                    .putString("position_profiles", "*|" + slValue + "," + tpValue + "," + ref.name)
                    .putBoolean("sl_tp_configured", true)
                    .apply()
                PositionTradeConfigStore.reload(this)
                send(MireiForegroundService.ACTION_APPLY_RISK)
            }
            .show()
    }

    private fun confirmReset() {
        AlertDialog.Builder(this)
            .setTitle("RESET")
            .setMessage("Reset sesi. History tetap tersimpan.")
            .setNegativeButton("BATAL", null)
            .setPositiveButton("RESET") { _, _ -> send(MireiForegroundService.ACTION_RESET_SESSION) }
            .show()
    }

    private fun isRiskConfigured(): Boolean =
        getSharedPreferences("mirei_settings", MODE_PRIVATE).getBoolean("sl_tp_configured", false) &&
            PositionTradeConfigStore.snapshot()["*"] != null

    private fun showRiskRequired() {
        AlertDialog.Builder(this)
            .setTitle("ATUR SL/TP WAJIB")
            .setMessage("Sebelum MULAI, tetapkan SL dan TP terlebih dahulu. Setelah disimpan, baru pilih instrument dan modal.")
            .setPositiveButton("ATUR SL/TP") { _, _ -> showRiskDialog() }
            .setNegativeButton("BATAL", null)
            .show()
    }

    private fun requestStatus() = send(MireiForegroundService.ACTION_STATUS)

    private fun send(action: String) {
        val intent = Intent(this, MireiForegroundService::class.java).apply { this.action = action }
        runCatching {
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
        }
    }

    private fun addSection(title: String) { content.addView(text(title, 16f, true), margin(0, 10, 0, 6)) }

    private fun tableRow(values: List<String>, header: Boolean): View {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(2, 4, 2, 4) }
        values.forEach { value ->
            row.addView(text(value, if (header) 10f else 9f, header), LinearLayout.LayoutParams(120, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        return row
    }

    private fun button(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { action() }
    }

    private fun card(value: String, size: Float = 14f): TextView = text(value, size).apply {
        setPadding(12, 12, 12, 12)
        setBackgroundColor(Color.rgb(55, 55, 55))
    }

    private fun text(value: String, size: Float, bold: Boolean = false): TextView = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(Color.WHITE)
        gravity = Gravity.START
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun margin(l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams =
        ViewGroup.MarginLayoutParams(-1, -2).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }

    private fun formatTime(epoch: Long): String =
        SimpleDateFormat("dd/MM HH:mm:ss", Locale.US).format(Date(epoch))
}
