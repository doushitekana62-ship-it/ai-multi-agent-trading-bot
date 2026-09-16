package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
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
import com.mirei.app.core.AssetClass
import com.mirei.app.core.Exchange
import com.mirei.app.core.ManualRiskMode
import com.mirei.app.core.PositionTradeConfig
import com.mirei.app.core.PositionTradeConfigStore
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
        val drafts = linkedMapOf<String, Draft>()
        val selectedChecks = linkedMapOf<String, CheckBox>()
        val amounts = linkedMapOf<String, EditText>()
        val instrumentList = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }

        form.addView(label(activity, "1. MARKET INSTRUMENT & MODAL", 16f, true))
        form.addView(label(activity, "Urutan: Exchange → Jenis Trade → Pair → kontrak TP/SL. Exchange yang belum memiliki adapter tidak dapat dimulai.", 12.5f))
        form.addView(label(activity, "EXCHANGE", 13f, true))
        val exchangeSpinner = Spinner(activity)
        exchangeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, Exchange.values().map { if (it.enabledForSixHourTest) it.label else "${it.label} · SEGERA" })
        form.addView(exchangeSpinner)
        form.addView(label(activity, "JENIS TRADE", 13f, true))
        val classSpinner = Spinner(activity)
        form.addView(classSpinner)
        val availability = label(activity, "", 11.5f)
        form.addView(availability)
        form.addView(instrumentList)
        form.addView(label(activity, "Total modal maksimal Rp150.000. Maksimal 3 posisi aktif.", 12.5f))
        form.addView(label(activity, "2. KONTRAK TRADE PER INSTRUMENT", 16f, true), lp(activity, 0, 8, 0, 0))
        form.addView(label(activity, "ATUR membuka konfigurasi khusus instrument. MANUAL mengunci mode AUTO/BALANCED/AGGRESSIVE/SAFETY agar TP/SL manual tidak tertimpa.", 12.5f))

        fun rebuildClasses(exchange: Exchange) {
            instrumentList.removeAllViews(); selectedChecks.clear(); amounts.clear()
            if (!exchange.enabledForSixHourTest) {
                classSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, listOf("Belum tersedia untuk uji 6 jam"))
                availability.text = "${exchange.label} belum memiliki adapter paper/data aktif pada build ini. Tidak ada pair yang dipalsukan."
                return
            }
            val supported = TradingUniverse.paperReady().filter { it.providerId == exchange.id }
            val classes = supported.map { it.assetClass }.distinct()
            classSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, classes.map { it.label })
            classSpinner.setSelection(0)
            fun rebuildInstruments(assetClass: AssetClass) {
                instrumentList.removeAllViews(); selectedChecks.clear(); amounts.clear()
                val instruments = supported.filter { it.assetClass == assetClass }
                availability.text = "${exchange.label} · ${assetClass.label} · ${instruments.size} instrument paper-ready dari provider ${exchange.id}."
                instruments.forEachIndexed { index, instrument ->
                    val draft = drafts.getOrPut(instrument.symbol) { Draft() }
                    val check = CheckBox(activity).apply { text = "${instrument.symbol} · ${instrument.name}\n${instrument.assetClass.label} · ${instrument.providerId.uppercase(Locale.US)} · quote ${instrument.quoteCurrency}"; textSize = 13.5f; isChecked = index < 3; minHeight = dp(activity, 58) }
                    val amount = EditText(activity).apply { hint = "Modal IDR"; textSize = 14f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(if (index < 3) "50000" else ""); isEnabled = check.isChecked; minHeight = dp(activity, 46) }
                    val configure = Button(activity).apply { text = "ATUR"; isAllCaps = false; minHeight = dp(activity, 44) }
                    val summary = TextView(activity).apply { textSize = 11f; setTextColor(Color.LTGRAY); setPadding(0, 0, dp(activity, 4), dp(activity, 4)) }
                    fun refreshSummary() { summary.text = draftLabel(draft); configure.setOnClickListener { configureTrade(activity, instrument.symbol, draft) { refreshSummary() } } }
                    refreshSummary()
                    check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked; configure.isEnabled = checked }
                    selectedChecks[instrument.symbol] = check; amounts[instrument.symbol] = amount
                    val left = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
                    left.addView(check); left.addView(summary)
                    val right = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
                    right.addView(amount, LinearLayout.LayoutParams(dp(activity, 128), ViewGroup.LayoutParams.WRAP_CONTENT)); right.addView(configure, LinearLayout.LayoutParams(dp(activity, 128), ViewGroup.LayoutParams.WRAP_CONTENT))
                    val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                    row.addView(left, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)); row.addView(right)
                    instrumentList.addView(row); instrumentList.addView(label(activity, "", 2f))
                }
            }
            classSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
                override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { classes.getOrNull(position)?.let(::rebuildInstruments) }
            }
            rebuildInstruments(classes.firstOrNull() ?: AssetClass.CRYPTO)
        }
        exchangeSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { rebuildClasses(Exchange.values().getOrElse(position) { Exchange.INDODAX }) }
        }
        rebuildClasses(Exchange.INDODAX)

        val dialog = AlertDialog.Builder(activity)
            .setTitle("MULAI SESI PAPER")
            .setView(scroll)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("MULAI", null)
            .create()
        dialog.setOnShowListener {
            dialog.window?.setLayout((activity.resources.displayMetrics.widthPixels * 0.96f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.90f).toInt())
            scroll.layoutParams = scroll.layoutParams.apply { height = (activity.resources.displayMetrics.heightPixels * 0.66f).toInt(); width = ViewGroup.LayoutParams.MATCH_PARENT }
            scroll.requestLayout()
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val exchange = Exchange.values().getOrElse(exchangeSpinner.selectedItemPosition) { Exchange.INDODAX }
                if (!exchange.enabledForSixHourTest) { dialog.setTitle("MULAI SESI PAPER · EXCHANGE BELUM TERSEDIA"); return@setOnClickListener }
                val selected = selectedChecks.mapNotNull { (symbol, check) -> if (!check.isChecked) null else amounts[symbol]?.text?.toString()?.toDoubleOrNull()?.takeIf { it > 0.0 }?.let { symbol to it } }
                if (selected.isEmpty() || selected.size > 3) { dialog.setTitle("MULAI SESI PAPER · pilih 1–3 instrument"); return@setOnClickListener }
                val total = selected.sumOf { it.second }
                if (total > 150_000.0 + 1e-6) { dialog.setTitle("MULAI SESI PAPER · modal melebihi Rp150.000"); return@setOnClickListener }
                val profileText = selected.joinToString(";") { (symbol, _) -> "$symbol|${encode(drafts[symbol] ?: Draft())}" }
                prefs.edit().putString("position_profiles", profileText).putString("mode", drafts[selected.first().first]?.mode?.name ?: ScalpingMode.BALANCED.name).putBoolean("manual_risk", false).putString("risk_basis", drafts[selected.first().first]?.basis?.name ?: RiskReferenceMode.ENTRY_PRICE.name).apply()
                PositionTradeConfigStore.reload(activity)
                val allocations = selected.joinToString(";") { "${it.first}=${it.second}" }
                val first = TradingUniverse.bySymbol(selected.first().first) ?: return@setOnClickListener
                val intent = Intent(activity, MireiForegroundService::class.java).apply { action = MireiForegroundService.ACTION_START; putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations); putExtra(MireiForegroundService.EXTRA_SYMBOL, first.symbol); putExtra(MireiForegroundService.EXTRA_EXCHANGE, exchange.id) }
                runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) }.onFailure { dialog.setTitle("MULAI SESI PAPER · gagal: ${it.message ?: "error"}"); return@setOnClickListener }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun configureTrade(activity: Activity, symbol: String, draft: Draft, onSaved: () -> Unit) {
        val box = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(activity, 12), dp(activity, 4), dp(activity, 12), dp(activity, 4)) }
        box.addView(label(activity, symbol, 18f, true))
        box.addView(label(activity, "Kontrak ini hanya berlaku untuk $symbol.", 12.5f))
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
        fun refresh() {
            val enabled = manual.isChecked
            sl.isEnabled = enabled; tpMode.isEnabled = enabled; tpPercent.isEnabled = enabled && tpMode.selectedItemPosition == 1; netTarget.isEnabled = enabled && tpMode.selectedItemPosition == 2
            mode.isEnabled = !enabled
            tpPercent.visibility = if (tpMode.selectedItemPosition == 1) View.VISIBLE else View.GONE
            netTarget.visibility = if (tpMode.selectedItemPosition == 2) View.VISIBLE else View.GONE
        }
        manual.setOnCheckedChangeListener { _, _ -> refresh() }
        tpMode.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener { override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit; override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { refresh() } }
        refresh()
        AlertDialog.Builder(activity).setTitle("JENIS TRADE · $symbol").setView(box).setNegativeButton("BATAL", null).setPositiveButton("SIMPAN") { _, _ ->
            val slValue = sl.text.toString().toDoubleOrNull(); val tpValue = tpPercent.text.toString().toDoubleOrNull(); val net = netTarget.text.toString().toDoubleOrNull(); val selectedTp = when (tpMode.selectedItemPosition) { 1 -> TakeProfitMode.MANUAL_PERCENT; 2 -> TakeProfitMode.MANUAL_NET_IDR; else -> TakeProfitMode.MODE }
            if (manual.isChecked && (slValue == null || slValue <= 0.0 || (selectedTp == TakeProfitMode.MANUAL_PERCENT && (tpValue == null || tpValue <= slValue)) || (selectedTp == TakeProfitMode.MANUAL_NET_IDR && (net == null || net <= 0.0)))) return@setPositiveButton
            draft.mode = runCatching { ScalpingMode.valueOf(mode.selectedItem.toString()) }.getOrDefault(ScalpingMode.BALANCED); draft.manual = manual.isChecked; draft.sl = slValue ?: 0.50; draft.tpMode = selectedTp; draft.tpPercent = tpValue ?: 1.00; draft.netTarget = net ?: 30.0; draft.basis = if (basis.checkedRadioButtonId == capital.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE; onSaved()
        }.show()
    }

    private fun draftLabel(draft: Draft): String = if (!draft.manual) "AUTO · ${draft.mode.name} · TP/SL mengikuti mode" else when (draft.tpMode) { TakeProfitMode.MANUAL_NET_IDR -> "MANUAL · SL ${draft.sl}% · TP bersih Rp${numberFormat.format(draft.netTarget)} · ${draft.basis.name}"; TakeProfitMode.MANUAL_PERCENT -> "MANUAL · SL ${draft.sl}% · TP ${draft.tpPercent}% · ${draft.basis.name}"; else -> "MANUAL · SL ${draft.sl}% · TP mode · ${draft.basis.name}" }
    private fun encode(d: Draft): String = listOf(d.mode.name, d.manual, d.sl, d.tpMode.name, d.tpPercent, d.netTarget, d.basis.name).joinToString(",")
    private fun label(activity: Activity, value: String, size: Float, bold: Boolean = false): TextView = TextView(activity).apply { text = value; textSize = size; setTextColor(Color.WHITE); setPadding(dp(activity, 4), dp(activity, 4), dp(activity, 4), dp(activity, 4)); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD) }
    private fun lp(activity: Activity, l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(-1, -2).apply { leftMargin = dp(activity, l); topMargin = dp(activity, t); rightMargin = dp(activity, r); bottomMargin = dp(activity, b) }
    private fun field(activity: Activity, hint: String, value: String): EditText = EditText(activity).apply { this.hint = hint; textSize = 14f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(value); minHeight = dp(activity, 46) }
    private fun dp(activity: Activity, value: Int): Int = (value * activity.resources.displayMetrics.density + 0.5f).toInt()
}
