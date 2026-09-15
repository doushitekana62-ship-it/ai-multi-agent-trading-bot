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
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.util.Locale

object MireiStartSessionDialog {
    private val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }

    fun show(activity: Activity) {
        val form = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(activity, 8), 0, dp(activity, 8), dp(activity, 8))
        }
        val scroll = ScrollView(activity).apply {
            isFillViewport = false
            addView(form, ViewGroup.LayoutParams(-1, -2))
        }

        form.addView(label(activity, "1. COIN & MODAL", 16f, true))
        form.addView(label(activity, "Pilih 1–3 coin. Modal pada baris coin menjadi modal beli pertama dan dapat menjadi acuan TP/SL.", 13f))
        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val rows = MireiForegroundService.SUPPORTED_MARKETS.mapIndexed { index, market ->
            val check = CheckBox(activity).apply {
                text = market
                textSize = 16f
                isChecked = index < 3
                minHeight = dp(activity, 52)
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
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(amount, LinearLayout.LayoutParams(dp(activity, 150), ViewGroup.LayoutParams.WRAP_CONTENT))
            list.addView(row)
            market to Pair(check, amount)
        }
        form.addView(list)

        form.addView(label(activity, "2. MODE TRADING", 16f, true), lp(activity, 0, 8, 0, 0))
        val prefs = activity.getSharedPreferences("mirei_settings", Activity.MODE_PRIVATE)
        val modeSpinner = Spinner(activity)
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        modeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, modes)
        modeSpinner.setSelection(modes.indexOf(prefs.getString("mode", "BALANCED")).coerceAtLeast(0))
        form.addView(modeSpinner, ViewGroup.LayoutParams(-1, dp(activity, 52)))

        form.addView(label(activity, "3. DASAR PEMANTAUAN TP / SL", 16f, true), lp(activity, 0, 8, 0, 0))
        val basisGroup = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL }
        val entryRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "Harga ENTRY COIN — TP/SL mengikuti harga entry posisi"; textSize = 15f }
        val capitalRadio = RadioButton(activity).apply { id = View.generateViewId(); text = "MODAL BELI PERTAMA — target/rugi IDR dihitung dari modal pertama coin"; textSize = 15f }
        basisGroup.addView(entryRadio)
        basisGroup.addView(capitalRadio)
        val savedBasis = prefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name)
        basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        form.addView(basisGroup)
        form.addView(label(activity, "Pada mode MODAL BELI PERTAMA, tiap coin memakai modal pada baris coin sebagai acuan. Contoh Rp50.000 tetap menjadi acuan walaupun harga entry berbeda.", 12.5f))

        form.addView(label(activity, "4. TP / SL", 16f, true), lp(activity, 0, 8, 0, 0))
        val manualSwitch = Switch(activity).apply { text = "TP / SL MANUAL"; textSize = 15f; isChecked = prefs.getBoolean("manual_risk", false) }
        form.addView(manualSwitch)
        val riskFields = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }
        val slField = EditText(activity).apply { hint = "SL %"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(prefs.getString("manual_sl", "0.50")); minHeight = dp(activity, 52) }
        val tpField = EditText(activity).apply { hint = "TP %"; textSize = 15f; setSingleLine(true); inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setText(prefs.getString("manual_tp", "1.00")); minHeight = dp(activity, 52) }
        riskFields.addView(slField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(activity, 8) })
        riskFields.addView(tpField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        riskFields.visibility = if (manualSwitch.isChecked) View.VISIBLE else View.GONE
        modeSpinner.isEnabled = !manualSwitch.isChecked
        manualSwitch.setOnCheckedChangeListener { _, checked ->
            riskFields.visibility = if (checked) View.VISIBLE else View.GONE
            modeSpinner.isEnabled = !checked
        }
        form.addView(riskFields)
        form.addView(label(activity, "Saat TP / SL MANUAL aktif, MODE TRADING dikunci agar konfigurasi risiko tidak berubah tanpa sengaja.", 12f))
        form.addView(label(activity, "Decision Mode: SUGGESTION\nMirei tetap memegang gate risiko, freshness, posisi, fee/slippage. Re-entry tidak dipaksa.", 12f), lp(activity, 0, 4, 0, 0))

        val dialog = AlertDialog.Builder(activity)
            .setTitle("MULAI SESI PAPER")
            .setMessage("Konfigurasi sesi sebelum runtime dimulai.")
            .setView(scroll)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("MULAI", null)
            .create()
        dialog.setOnShowListener {
            // Keep the action buttons outside the scrollable form. The form gets a
            // bounded height so MULAI/BATAL remain visible on short phone screens.
            dialog.window?.setLayout((activity.resources.displayMetrics.widthPixels * 0.94f).toInt(), (activity.resources.displayMetrics.heightPixels * 0.88f).toInt())
            scroll.layoutParams = scroll.layoutParams.apply {
                height = (activity.resources.displayMetrics.heightPixels * 0.58f).toInt()
                width = ViewGroup.LayoutParams.MATCH_PARENT
            }
            scroll.requestLayout()
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val selected = rows.mapNotNull { (market, pair) ->
                    val (check, amount) = pair
                    if (!check.isChecked) null else amount.text.toString().toDoubleOrNull()?.takeIf { it > 0.0 }?.let { market to it }
                }
                if (selected.isEmpty() || selected.size > 3) { dialog.setMessage("Pilih minimal 1 dan maksimal 3 coin, dengan modal > 0."); return@setOnClickListener }
                val total = selected.sumOf { it.second }
                if (total > 150_000.0 + 1e-6) { dialog.setMessage("Total modal Rp ${numberFormat.format(total)} melebihi Rp150.000."); return@setOnClickListener }
                val manual = manualSwitch.isChecked
                val sl = slField.text.toString().toDoubleOrNull()
                val tp = tpField.text.toString().toDoubleOrNull()
                if (manual && (sl == null || tp == null || sl <= 0.0 || tp <= sl)) { dialog.setMessage("TP manual harus lebih besar dari SL manual dan keduanya harus > 0."); return@setOnClickListener }
                val mode = modeSpinner.selectedItem.toString()
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                prefs.edit().putString("mode", mode).putBoolean("manual_risk", manual).putString("manual_sl", (sl ?: 0.50).toString()).putString("manual_tp", (tp ?: 1.00).toString()).putString("risk_basis", basisMode.name).apply()
                val allocations = selected.joinToString(";") { "${it.first}=${it.second}" }
                val intent = Intent(activity, MireiForegroundService::class.java).apply {
                    action = MireiForegroundService.ACTION_START
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations)
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, selected.first().first)
                    putExtra(MireiForegroundService.EXTRA_EXCHANGE, "indodax")
                }
                runCatching {
                    if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent)
                }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun label(activity: Activity, value: String, size: Float, bold: Boolean = false): TextView = TextView(activity).apply {
        text = value; textSize = size; setTextColor(android.graphics.Color.WHITE); setPadding(dp(activity, 4), dp(activity, 4), dp(activity, 4), dp(activity, 4))
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun lp(activity: Activity, l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams = ViewGroup.MarginLayoutParams(-1, -2).apply {
        leftMargin = dp(activity, l); topMargin = dp(activity, t); rightMargin = dp(activity, r); bottomMargin = dp(activity, b)
    }

    private fun dp(activity: Activity, value: Int): Int = (value * activity.resources.displayMetrics.density + 0.5f).toInt()
}
