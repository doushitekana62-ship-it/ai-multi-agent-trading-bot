package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
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
import com.mirei.app.core.TradingUniverse
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.util.Locale

object MireiStartSessionDialog {
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }

    fun show(activity: Activity) {
        val form = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(activity, 8), 0, dp(activity, 8), dp(activity, 8)) }
        val scroll = ScrollView(activity).apply { isFillViewport = false; addView(form, ViewGroup.LayoutParams(-1, -2)) }
        val prefs = activity.getSharedPreferences("mirei_settings", Activity.MODE_PRIVATE)
        val instruments = TradingUniverse.paperReady()

        form.addView(label(activity, "1. MARKET INSTRUMENT & MODAL", 16f, true))
        form.addView(label(activity, "Pilih 1–3 instrument yang tersedia pada provider masing-masing. Mirei tidak menganggap semua exchange menyediakan semua jenis pasar.", 13f))
        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val rows = instruments.mapIndexed { index, instrument ->
            val check = CheckBox(activity).apply {
                text = "${instrument.symbol} · ${instrument.assetClass.label}\n${instrument.name} · ${instrument.providerId.uppercase(Locale.US)} · quote ${instrument.quoteCurrency}"
                textSize = 14f
                isChecked = index < 3
                minHeight = dp(activity, 60)
                setPadding(0, dp(activity, 4), dp(activity, 4), dp(activity, 4))
            }
            val amount = EditText(activity).apply {
                hint = "Modal IDR"
                textSize = 15f
                setSingleLine(true)
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                setText(if (index < 3) "50000" else "")
                isEnabled = check.isChecked
                minHeight = dp(activity, 52)
            }
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(amount, LinearLayout.LayoutParams(dp(activity, 145), ViewGroup.LayoutParams.WRAP_CONTENT))
            list.addView(row)
            instrument to Pair(check, amount)
        }
        form.addView(list)

        form.addView(label(activity, "2. MODE TRADING", 16f, true), lp(activity, 0, 8, 0, 0))
        val modeSpinner = Spinner(activity)
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        modeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, modes)
        modeSpinner.setSelection(modes.indexOf(prefs.getString("mode", "BALANCED")).coerceAtLeast(0))
        form.addView(modeSpinner, ViewGroup.LayoutParams(-1, dp(activity, 52)))

        form.addView(label(activity, "3. DASAR PEMANTAUAN TP / SL", 16f, true), lp(activity, 0, 8, 0, 0))
        val basisGroup = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL }
        val entryRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "Harga ENTRY — TP/SL mengikuti harga eksekusi posisi"; textSize = 15f }
        val capitalRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "MODAL BELI PERTAMA — risiko/target memakai modal siklus pertama"; textSize = 15f }
        basisGroup.addView(entryRadio); basisGroup.addView(capitalRadio)
        val savedBasis = prefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name)
        basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        form.addView(basisGroup)
        form.addView(label(activity, "Pada mode MODAL BELI PERTAMA, re-entry memakai modal siklus pertama dan tidak otomatis menggabungkan profit TP ke modal berikutnya.", 12.5f))

        form.addView(label(activity, "4. TP / SL", 16f, true), lp(activity, 0, 8, 0, 0))
        val manualSwitch = Switch(activity).apply { text = "TP / SL MANUAL"; textSize = 15f; isChecked = prefs.getBoolean("manual_risk", false) }
        form.addView(manualSwitch)
        val riskFields = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }
        val slField = EditText(activity).apply { hint = "SL %"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(prefs.getString("manual_sl", "0.50")); minHeight = dp(activity, 52) }
        val netTargetField = EditText(activity).apply { hint = "Target profit bersih Rp"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(prefs.getString("manual_net_target", "30")); minHeight = dp(activity, 52) }
        riskFields.addView(slField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 0.8f).apply { rightMargin = dp(activity, 8) })
        riskFields.addView(netTargetField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.2f))
        riskFields.visibility = if (manualSwitch.isChecked) View.VISIBLE else View.GONE
        modeSpinner.isEnabled = !manualSwitch.isChecked
        manualSwitch.setOnCheckedChangeListener { _, checked -> riskFields.visibility = if (checked) View.VISIBLE else View.GONE; modeSpinner.isEnabled = !checked }
        form.addView(riskFields)
        form.addView(label(activity, "Target profit bersih dihitung setelah biaya instrument, spread dan slippage simulasi. Contoh: Rp30 berarti Mirei baru menutup TP jika hasil bersih minimal Rp30.", 12f))
        form.addView(label(activity, "Saat TP / SL MANUAL aktif, mode AGGRESSIVE/BALANCED/SAFETY tidak menjadi sumber TP/SL.", 12f))
        form.addView(label(activity, "Decision Mode: SUGGESTION\nGate risiko, freshness, posisi, fee/slippage dan re-entry tetap dikendalikan Mirei.", 12f), lp(activity, 0, 4, 0, 0))

        val dialog = AlertDialog.Builder(activity).setTitle("MULAI SESI PAPER").setMessage("Konfigurasi sesi sebelum runtime dimulai.").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.window?.setLayout((activity.resources.displayMetrics.widthPixels * 0.94f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.88f).toInt())
            scroll.layoutParams = scroll.layoutParams.apply { height = (activity.resources.displayMetrics.heightPixels * 0.58f).toInt(); width = ViewGroup.LayoutParams.MATCH_PARENT }
            scroll.requestLayout()
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val selected = rows.mapNotNull { (instrument, pair) ->
                    val (check, amount) = pair
                    if (!check.isChecked) null else amount.text.toString().toDoubleOrNull()?.takeIf { it > 0.0 }?.let { instrument to it }
                }
                if (selected.isEmpty() || selected.size > 3) { dialog.setMessage("Pilih minimal 1 dan maksimal 3 instrument, dengan modal > 0."); return@setOnClickListener }
                val total = selected.sumOf { it.second }
                if (total > 150_000.0 + 1e-6) { dialog.setMessage("Total modal Rp ${numberFormat.format(total)} melebihi Rp150.000."); return@setOnClickListener }
                val manual = manualSwitch.isChecked
                val sl = slField.text.toString().toDoubleOrNull()
                val netTarget = netTargetField.text.toString().toDoubleOrNull()
                if (manual && (sl == null || sl <= 0.0 || netTarget == null || netTarget <= 0.0)) { dialog.setMessage("SL manual harus > 0 dan target profit bersih harus > Rp0."); return@setOnClickListener }
                val mode = modeSpinner.selectedItem.toString()
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                prefs.edit().putString("mode", mode).putBoolean("manual_risk", manual).putString("manual_sl", (sl ?: 0.50).toString()).putString("manual_tp", "1.00").putString("manual_net_target", (netTarget ?: 30.0).toString()).putString("risk_basis", basisMode.name).apply()
                val allocations = selected.joinToString(";") { "${it.first.symbol}=${it.second}" }
                val selectedInstrument = selected.first().first
                val intent = Intent(activity, MireiForegroundService::class.java).apply {
                    action = MireiForegroundService.ACTION_START
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations)
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, selectedInstrument.symbol)
                    putExtra(MireiForegroundService.EXTRA_EXCHANGE, selectedInstrument.providerId)
                }
                runCatching { if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent) }
                    .onFailure { dialog.setMessage("Sesi tidak dapat dimulai: ${it.message ?: "error"}"); return@setOnClickListener }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun label(activity: Activity, value: String, size: Float, bold: Boolean = false): TextView = TextView(activity).apply { text = value; textSize = size; setTextColor(android.graphics.Color.WHITE); setPadding(dp(activity, 4), dp(activity, 4), dp(activity, 4), dp(activity, 4)); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD) }
    private fun lp(activity: Activity, l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(-1, -2).apply { leftMargin = dp(activity, l); topMargin = dp(activity, t); rightMargin = dp(activity, r); bottomMargin = dp(activity, b) }
    private fun dp(activity: Activity, value: Int): Int = (value * activity.resources.displayMetrics.density + 0.5f).toInt()
}
