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
import com.mirei.app.runtime.MultiMarketDataSource

object MireiStartSessionDialog {
    fun show(activity: Activity, onStarting: () -> Unit = {}) {
        val form = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 8, 12, 8) }
        val scroll = ScrollView(activity).apply { addView(form, ViewGroup.LayoutParams(-1, -2)) }
        form.addView(label(activity, "PAPER MARKET", 18f, true))
        form.addView(label(activity, "Pilih saham, forex, kripto, atau komoditas/emas. Broker tidak dikunci pada dashboard.", 12.5f))

        val exchangeSpinner = Spinner(activity)
        val exchangeOptions = com.mirei.app.core.Exchange.values()
        exchangeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, exchangeOptions.map { it.label })
        form.addView(label(activity, "EXCHANGE", 12f, true))
        form.addView(exchangeSpinner)

        val classSpinner = Spinner(activity)
        form.addView(label(activity, "JENIS TRADE", 12f, true))
        form.addView(classSpinner)
        val instruments = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        form.addView(instruments)

        fun rebuild(assetClass: AssetClass) {
            instruments.removeAllViews()
            val exchange = exchangeOptions.getOrElse(exchangeSpinner.selectedItemPosition) { exchangeOptions.first() }
            TradingUniverse.paperReady().filter { it.assetClass == assetClass && it.providerId == exchange.id }.forEachIndexed { index, instrument ->
                val check = CheckBox(activity).apply { text = "${instrument.symbol} · ${instrument.name}"; textSize = 13.5f; isChecked = index == 0 }
                val amount = EditText(activity).apply { hint = "Nominal beli"; inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL; setSingleLine(true); setText(if (index == 0) "50000" else ""); isEnabled = check.isChecked }
                check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
                val row = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL; setPadding(4, 3, 4, 3) }
                row.addView(check)
                val price = label(activity, "${instrument.symbol} · memuat harga...", 10.5f)
                row.addView(price)
                row.addView(amount)
                row.tag = instrument.symbol
                instruments.addView(row)
                Thread {
                    val snapshot = runCatching { MultiMarketDataSource().snapshot(instrument.symbol) }.getOrNull()
                    activity.runOnUiThread {
                        val nf = java.text.NumberFormat.getNumberInstance(java.util.Locale("id", "ID"))
                        price.text = if (snapshot != null && snapshot.price > 0.0) "${instrument.symbol} · Rp ${nf.format(snapshot.price)} / 1 coin" else "${instrument.symbol} · harga belum tersedia"
                    }
                }.start()
            }
            if (instruments.childCount == 0) instruments.addView(label(activity, "Belum ada instrument paper untuk exchange ini.", 12f))
        }

        fun rebuildClasses(exchange: com.mirei.app.core.Exchange) {
            val classes = AssetClass.values().filter { asset -> TradingUniverse.paperReady().any { it.assetClass == asset && it.providerId == exchange.id } }
            classSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, classes.map { it.label })
            rebuild(classes.firstOrNull() ?: AssetClass.CRYPTO)
        }
        classSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val classes = AssetClass.values().filter { asset -> TradingUniverse.paperReady().any { it.assetClass == asset && it.providerId == exchangeOptions.getOrElse(exchangeSpinner.selectedItemPosition) { exchangeOptions.first() }.id } }
                rebuild(classes.getOrElse(position) { AssetClass.CRYPTO })
            }
        }
        exchangeSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { rebuildClasses(exchangeOptions.getOrElse(position) { exchangeOptions.first() }) }
        }
        rebuildClasses(exchangeOptions.first())


        val dialog = AlertDialog.Builder(activity).setTitle("MULAI PAPER").setView(scroll).setNegativeButton("BATAL", null).setPositiveButton("MULAI", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val allocations = linkedMapOf<String, Double>()
                for (i in 0 until instruments.childCount) {
                    val row = instruments.getChildAt(i) as? LinearLayout ?: continue
                    val check = row.getChildAt(0) as? CheckBox ?: continue
                    val amount = row.getChildAt(2) as? EditText ?: continue
                    if (!check.isChecked) continue
                    val symbol = row.tag as? String ?: continue
                    val value = amount.text.toString().toDoubleOrNull() ?: 0.0
                    if (value > 0.0) allocations[symbol] = value
                }
                if (allocations.isEmpty()) { dialog.setTitle("Pilih minimal 1 posisi"); return@setOnClickListener }
                if (allocations.size > 10) { dialog.setTitle("Maksimal 10 posisi"); return@setOnClickListener }
                if (allocations.values.fold(0.0) { acc, value -> acc + value } > 150_000.0 + 1e-6) { dialog.setTitle("Total modal maksimal Rp150.000"); return@setOnClickListener }
                val first = allocations.keys.first()
                val raw = allocations.entries.joinToString(";") { "${it.key}=${it.value}" }
                val intent = Intent(activity, MireiForegroundService::class.java).apply {
                    action = MireiForegroundService.ACTION_START
                    putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, raw)
                    putExtra(MireiForegroundService.EXTRA_SYMBOL, first)
                }
                onStarting()
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
        dialog.window?.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE or android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN)
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
