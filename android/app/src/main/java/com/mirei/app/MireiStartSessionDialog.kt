package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import com.mirei.app.core.AssetClass
import com.mirei.app.core.TradingUniverse
import com.mirei.app.runtime.MireiForegroundService

object MireiStartSessionDialog {
    fun show(activity: Activity) {
        val form = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 8, 12, 8) }
        val scroll = ScrollView(activity).apply { addView(form, ViewGroup.LayoutParams(-1, -2)) }
        form.addView(label(activity, "PAPER MARKET", 18f, true))
        form.addView(label(activity, "Pilih saham, forex, kripto, atau komoditas/emas. Broker tidak dikunci pada dashboard.", 12.5f))

        val classSpinner = Spinner(activity)
        classSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, AssetClass.values().map { it.label })
        form.addView(classSpinner)

        val instruments = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        form.addView(instruments)

        fun rebuild(assetClass: AssetClass) {
            instruments.removeAllViews()
            TradingUniverse.paperReady().filter { it.assetClass == assetClass }.forEachIndexed { index, instrument ->
                val check = CheckBox(activity).apply {
                    text = "${instrument.symbol} · ${instrument.name}"
                    textSize = 13.5f
                    isChecked = index == 0
                }
                val amount = EditText(activity).apply {
                    hint = "Modal IDR"
                    inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                    setSingleLine(true)
                    setText(if (index == 0) "50000" else "")
                    isEnabled = check.isChecked
                }
                check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
                val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }
                row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                row.addView(amount, LinearLayout.LayoutParams(130, ViewGroup.LayoutParams.WRAP_CONTENT))
                row.tag = instrument.symbol
                instruments.addView(row)
            }
        }

        classSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                rebuild(AssetClass.values().getOrElse(position) { AssetClass.CRYPTO })
            }
        }
        rebuild(AssetClass.CRYPTO)

        val dialog = AlertDialog.Builder(activity).setTitle("MULAI PAPER").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val allocations = linkedMapOf<String, Double>()
                for (i in 0 until instruments.childCount) {
                    val row = instruments.getChildAt(i) as? LinearLayout ?: continue
                    val check = row.getChildAt(0) as? CheckBox ?: continue
                    val amount = row.getChildAt(1) as? EditText ?: continue
                    if (!check.isChecked) continue
                    val symbol = row.tag as? String ?: continue
                    val value = amount.text.toString().toDoubleOrNull() ?: 0.0
                    if (value > 0.0) allocations[symbol] = value
                }
                if (allocations.isEmpty()) { dialog.setTitle("Pilih minimal 1 posisi"); return@setOnClickListener }
                if (allocations.size > 10) { dialog.setTitle("Maksimal 10 posisi"); return@setOnClickListener }
                if (allocations.sumOf { it.value } > 150_000.0 + 1e-6) { dialog.setTitle("Total modal maksimal Rp150.000"); return@setOnClickListener }
                val first = allocations.keys.first()
                val raw = allocations.entries.joinToString(";") { "${it.key}=${it.value}" }
                val intent = Intent(activity, MireiForegroundService::class.java).apply {
                    action = MireiForegroundService.ACTION_START
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, raw)
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, first)
                }
                runCatching {
                    if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent)
                }.onFailure {
                    dialog.setTitle("Gagal memulai: ${it.message ?: "error"}")
                    return@setOnClickListener
                }
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun label(activity: Activity, value: String, size: Float, bold: Boolean = false): TextView =
        TextView(activity).apply {
            text = value
            textSize = size
            setTextColor(Color.WHITE)
            setPadding(4, 6, 4, 6)
            if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
}
