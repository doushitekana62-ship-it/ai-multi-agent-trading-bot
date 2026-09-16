package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.PositionTradeConfig
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.core.ScalpingMode
import com.mirei.app.core.TakeProfitMode
import com.mirei.app.core.TradingUniverse
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.util.Locale

object MireiStartSessionDialog {
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
    private data class Draft(var mode: ScalpingMode = ScalpingMode.BALANCED, var manual: Boolean = false, var sl: Double = 0.50, var tpMode: TakeProfitMode = TakeProfitMode.MANUAL_NET_IDR, var tpPercent: Double = 1.00, var netTarget: Double = 30.0, var basis: RiskReferenceMode = RiskReferenceMode.ENTRY_PRICE)

    fun show(activity: Activity) {
        val prefs = activity.getSharedPreferences("mirei_settings", Activity.MODE_PRIVATE)
        val form = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(activity, 8), 0, dp(activity, 8), dp(activity, 8)) }
        val scroll = ScrollView(activity).apply { isFillViewport = false; addView(form, ViewGroup.LayoutParams(-1, -2)) }
        form.addView(label(activity, "1. MARKET INSTRUMENT & MODAL", 16f, true))
        form.addView(label(activity, "Setiap instrument memiliki konfigurasi trade sendiri. Mode dan TP/SL BTC tidak mengubah ETH atau market lain.", 13f))
        val drafts = linkedMapOf<String, Draft>()
        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val rows = TradingUniverse.paperReady().mapIndexed { index, instrument ->
            val check = CheckBox(activity).apply { text = "${instrument.symbol} · ${instrument.assetClass.label}\n${instrument.name} · ${instrument.providerId.uppercase(Locale.US)} · quote ${instrument.quoteCurrency}"; textSize = 14f; isChecked = index < 3; minHeight = dp(activity, 58) }
            val amount = EditText(activity).apply { hint = "Modal IDR"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(if (index < 3) "50000" else ""); isEnabled = check.isChecked; minHeight = dp(activity, 48) }
            val draft = Draft()
            drafts[instrument.symbol] = draft
            val configure = Button(activity).apply { text = "ATUR"; isAllCaps = false; minHeight = dp(activity, 44) }
            val summary = TextView(activity).apply { textSize = 11.5f; setTextColor(android.graphics.Color.LTGRAY); setPadding(0, 0, dp(activity, 4), dp(activity, 4)) }
            fun refreshSummary() { summary.text = draftLabel(draft); configure.setOnClickListener { configureTrade(activity, instrument.symbol, draft) { refreshSummary() } } }
            refreshSummary()
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked; configure.isEnabled = checked }
            val left = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
            left.addView(check)
            left.addView(summary)
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            row.addView(left, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            val right = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
            right.addView(amount, LinearLayout.LayoutParams(dp(activity, 132), ViewGroup.LayoutParams.WRAP_CONTENT))
            right.addView(configure, LinearLayout.LayoutParams(dp(activity, 132), ViewGroup.LayoutParams.WRAP_CONTENT))
            row.addView(right)
            list.addView(row)
            list.addView(label(activity, "", 3f))
            instrument to Pair(check, amount)
        }
        form.addView(list)
        form.addView(label(activity, "Total modal maksimal Rp150.000. Maksimal 3 posisi aktif.", 12.5f))
        form.addView(label(activity, "2. KONTRAK TRADE PER INSTRUMENT", 16f, true), lp(activity, 0, 8, 0, 0))
        form.addView(label(activity, "ATUR membuka cabang konfigurasi: AUTO/AGGRESSIVE/BALANCED/SAFETY atau MANUAL. Pada MANUAL, TP dapat berupa persen atau target profit bersih IDR.", 12.5f))

        val dialog = AlertDialog.Builder(activity).setTitle("MULAI SESI PAPER").setMessage("Konfigurasi sesi sebelum runtime dimulai.").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.window?.setLayout((activity.resources.displayMetrics.widthPixels * 0.96f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.90f).toInt())
            scroll.layoutParams = scroll.layoutParams.apply { height = (activity.resources.displayMetrics.heightPixels * 0.72f).toInt(); width = ViewGroup.LayoutParams.MATCH_PARENT }
            scroll.requestLayout()
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val selected = rows.mapNotNull { (instrument, pair) -> val (check, amount) = pair; if (!check.isChecked) null else amount.text.toString().toDoubleOrNull()?.takeIf { it > 0.0 }?.let { instrument to it } }
                if (selected.isEmpty() || selected.size > 3) { dialog.setMessage("Pilih minimal 1 dan maksimal 3 instrument, dengan modal > 0."); return@setOnClickListener }
                val total = selected.sumOf { it.second }
                if (total > 150_000.0 + 1e-6) { dialog.setMessage("Total modal Rp ${numberFormat.format(total)} melebihi Rp150.000."); return@setOnClickListener }
                val profileText = selected.joinToString(";") { (instrument, _) -> "${instrument.symbol}|${encode(drafts[instrument.symbol] ?: Draft())}" }
                prefs.edit().putString("position_profiles", profileText).putString("mode", drafts[selected.first().first.symbol]?.mode?.name ?: ScalpingMode.BALANCED.name).putBoolean("manual_risk", false).putString("risk_basis", drafts[selected.first().first.symbol]?.basis?.name ?: RiskReferenceMode.ENTRY_PRICE.name).apply()
                val allocations = selected.joinToString(";") { "${it.first.symbol}=${it.second}" }
                val selectedInstrument = selected.first().first
                val intent = Intent(activity, MireiForegroundService::class.java).apply { action = MireiForegroundService.ACTION_START; putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations); putExtra(MireiForegroundService.EXTRA_SYMBOL, selectedInstrument.symbol); putExtra(MireiForegroundService.EXTRA_EXCHANGE, selectedInstrument.providerId) }
                runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) }.onFailure { dialog.setMessage("Sesi tidak dapat dimulai: ${it.message ?: "error"}"); return@setOnClickListener }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun configureTrade(activity: Activity, symbol: String, draft: Draft, onSaved: () -> Unit) {
        val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(activity, 12), dp(activity, 4), dp(activity, 12), dp(activity, 4)) }
        box.addView(label(activity, symbol, 18f, true))
        box.addView(label(activity, "Pilih jenis trade untuk instrument ini saja.", 12.5f))
        val mode = Spinner(activity).apply { adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, ScalpingMode.values().map { it.name }); setSelection(ScalpingMode.values().indexOf(draft.mode).coerceAtLeast(0)) }
        val manual = CheckBox(activity).apply { text = "MANUAL TP / SL"; isChecked = draft.manual }
        box.addView(label(activity, "MODE TRADE", 14f, true)); box.addView(mode); box.addView(manual)
        val sl = field(activity, "SL %", draft.sl.toString())
        val tpMode = Spinner(activity).apply { adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, arrayOf("MODE", "MANUAL_PERCENT", "MANUAL_NET_IDR")); setSelection(when (draft.tpMode) { TakeProfitMode.MODE -> 0; TakeProfitMode.MANUAL_PERCENT -> 1; TakeProfitMode.MANUAL_NET_IDR -> 2 }) }
        val tpPercent = field(activity, "TP %", draft.tpPercent.toString())
        val netTarget = field(activity, "Target profit bersih Rp", draft.netTarget.toString())
        val basis = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL }
        val entry = RadioButton(activity).apply { id = View.generateViewId(); text = "Harga ENTRY" }
        val capital = RadioButton(activity).apply { id = View.generateViewId(); text = "MODAL BELI PERTAMA" }
        basis.addView(entry); basis.addView(capital); basis.check(if (draft.basis == RiskReferenceMode.INITIAL_CAPITAL) capital.id else entry.id)
        box.addView(label(activity, "STOP LOSS", 14f, true)); box.addView(sl)
        box.addView(label(activity, "TAKE PROFIT", 14f, true)); box.addView(tpMode); box.addView(tpPercent); box.addView(netTarget)
        box.addView(label(activity, "DASAR RISIKO", 14f, true)); box.addView(basis)
        fun refresh() { val enabled = manual.isChecked; sl.isEnabled = enabled; tpMode.isEnabled = enabled; tpPercent.isEnabled = enabled && tpMode.selectedItemPosition == 1; netTarget.isEnabled = enabled && tpMode.selectedItemPosition == 2; mode.isEnabled = !enabled; tpPercent.visibility = if (tpMode.selectedItemPosition == 1) View.VISIBLE else View.GONE; netTarget.visibility = if (tpMode.selectedItemPosition == 2) View.VISIBLE else View.GONE }
        manual.setOnCheckedChangeListener { _, _ -> refresh() }; tpMode.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener { override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit; override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { refresh() } }; refresh()
        AlertDialog.Builder(activity).setTitle("JENIS TRADE · $symbol").setMessage("Kontrak ini hanya berlaku untuk $symbol.").setView(box).setNegativeButton("BATAL", null).setPositiveButton("SIMPAN") { _, _ ->
            val slValue = sl.text.toString().toDoubleOrNull(); val tpValue = tpPercent.text.toString().toDoubleOrNull(); val net = netTarget.text.toString().toDoubleOrNull(); val selectedTp = when (tpMode.selectedItemPosition) { 1 -> TakeProfitMode.MANUAL_PERCENT; 2 -> TakeProfitMode.MANUAL_NET_IDR; else -> TakeProfitMode.MODE }
            if (manual.isChecked && (slValue == null || slValue <= 0.0 || (selectedTp == TakeProfitMode.MANUAL_PERCENT && (tpValue == null || tpValue <= slValue)) || (selectedTp == TakeProfitMode.MANUAL_NET_IDR && (net == null || net <= 0.0)))) return@setPositiveButton
            draft.mode = runCatching { ScalpingMode.valueOf(mode.selectedItem.toString()) }.getOrDefault(ScalpingMode.BALANCED); draft.manual = manual.isChecked; draft.sl = slValue ?: 0.50; draft.tpMode = selectedTp; draft.tpPercent = tpValue ?: 1.00; draft.netTarget = net ?: 30.0; draft.basis = if (basis.checkedRadioButtonId == capital.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE; onSaved()
        }.show()
    }

    private fun draftLabel(draft: Draft): String = if (!draft.manual) "AUTO · ${draft.mode.name} · TP/SL mengikuti mode" else when (draft.tpMode) { TakeProfitMode.MANUAL_NET_IDR -> "MANUAL · SL ${draft.sl}% · TP bersih Rp${numberFormat.format(draft.netTarget)} · ${draft.basis.name}"; TakeProfitMode.MANUAL_PERCENT -> "MANUAL · SL ${draft.sl}% · TP ${draft.tpPercent}% · ${draft.basis.name}"; else -> "MANUAL · SL ${draft.sl}% · TP mode · ${draft.basis.name}" }
    private fun encode(d: Draft): String = listOf(d.mode.name, d.manual, d.sl, d.tpMode.name, d.tpPercent, d.netTarget, d.basis.name).joinToString(",")
    private fun label(activity: Activity, value: String, size: Float, bold: Boolean = false): TextView = TextView(activity).apply { text = value; textSize = size; setTextColor(android.graphics.Color.WHITE); setPadding(dp(activity, 4), dp(activity, 4), dp(activity, 4), dp(activity, 4)); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD) }
    private fun lp(activity: Activity, l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(-1, -2).apply { leftMargin = dp(activity, l); topMargin = dp(activity, t); rightMargin = dp(activity, r); bottomMargin = dp(activity, b) }
    private fun field(activity: Activity, hint: String, value: String): EditText = EditText(activity).apply { this.hint = hint; textSize = 14f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(value); minHeight = dp(activity, 46) }
    private fun dp(activity: Activity, value: Int): Int = (value * activity.resources.displayMetrics.density + 0.5f).toInt()
}
