package com.mirei.app

import android.app.Activity
import android.app.AlertDialog
import android.app.Application
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.text.InputType
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
import android.widget.Switch
import android.widget.TextView
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.runtime.MireiForegroundService
import java.text.NumberFormat
import java.util.Locale

/**
 * UI compatibility layer for the programmatic MainActivity.
 *
 * It keeps MainActivity's existing controls and runtime behavior intact, but
 * replaces only the Start button's cramped dialog with a scrollable form.
 */
class MireiUiPatchApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : ActivityLifecycleCallbacks {
            override fun onActivityResumed(activity: Activity) {
                if (activity is MainActivity) installStartButtonPatch(activity)
            }
            override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit
            override fun onActivityStarted(activity: Activity) = Unit
            override fun onActivityPaused(activity: Activity) = Unit
            override fun onActivityStopped(activity: Activity) = Unit
            override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
            override fun onActivityDestroyed(activity: Activity) = Unit
        })
    }

    private fun installStartButtonPatch(activity: Activity) {
        val root = activity.window.decorView
        fun patch() {
            findButtons(root).filter { it.text?.toString() == "MULAI" }.forEach { button ->
                if (button.getTag(TAG_PATCHED) == true) return@forEach
                button.setTag(TAG_PATCHED, true)
                button.setOnClickListener { showStartDialog(activity) }
            }
        }
        patch()
        val observer = root.viewTreeObserver
        if (observer.isAlive && root.getTag(TAG_OBSERVER) != true) {
            root.setTag(TAG_OBSERVER, true)
            observer.addOnGlobalLayoutListener { patch() }
        }
    }

    private fun findButtons(view: View): List<Button> {
        if (view is Button) return listOf(view)
        if (view !is ViewGroup) return emptyList()
        return buildList {
            for (index in 0 until view.childCount) addAll(findButtons(view.getChildAt(index)))
        }
    }

    private fun showStartDialog(activity: Activity) {
        val prefs = activity.getSharedPreferences("mirei_settings", Context.MODE_PRIVATE)
        val numberFormat = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 2 }
        val scroll = ScrollView(activity).apply { isFillViewport = true }
        val outer = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(16, 8, 16, 12)
        }
        scroll.addView(outer, ViewGroup.LayoutParams(-1, -2))

        outer.addView(label(activity, "1. COIN & MODAL", true))
        outer.addView(label(activity, "Pilih 1–3 coin. Modal pada baris coin menjadi modal beli pertama. Form dapat di-scroll; tombol MULAI tetap di bawah dialog.", false))

        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val rows = MireiForegroundService.SUPPORTED_MARKETS.mapIndexed { index, market ->
            val check = CheckBox(activity).apply {
                text = market
                textSize = 15f
                isChecked = index < 3
            }
            val amount = EditText(activity).apply {
                hint = "Modal IDR"
                textSize = 15f
                setSingleLine(true)
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                setText(if (index < 3) "50000" else "")
                isEnabled = check.isChecked
                setPadding(8, 4, 8, 4)
            }
            check.setOnCheckedChangeListener { _, checked -> amount.isEnabled = checked }
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = android.view.Gravity.CENTER_VERTICAL
                setPadding(4, 5, 4, 5)
            }
            row.addView(check, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(amount, LinearLayout.LayoutParams(132, ViewGroup.LayoutParams.WRAP_CONTENT))
            list.addView(row)
            market to Pair(check, amount)
        }
        outer.addView(list, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT))

        outer.addView(label(activity, "2. MODE TRADING", true))
        val modeSpinner = Spinner(activity)
        val modes = arrayOf("AGGRESSIVE", "BALANCED", "SAFETY")
        modeSpinner.adapter = ArrayAdapter(activity, android.R.layout.simple_spinner_dropdown_item, modes)
        modeSpinner.setSelection(modes.indexOf(prefs.getString("mode", "BALANCED")).coerceAtLeast(0))
        outer.addView(modeSpinner, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT))

        outer.addView(label(activity, "3. DASAR PEMANTAUAN TP / SL", true))
        val basisGroup = RadioGroup(activity).apply { orientation = RadioGroup.VERTICAL }
        val entryRadio = RadioButton(activity).apply {
            id = View.generateViewId()
            text = "Harga ENTRY COIN — pendekatan harga entry tetap tersedia"
            textSize = 15f
        }
        val capitalRadio = RadioButton(activity).apply {
            id = View.generateViewId()
            text = "MODAL BELI PERTAMA — target/rugi IDR dari modal pertama coin"
            textSize = 15f
        }
        basisGroup.addView(entryRadio)
        basisGroup.addView(capitalRadio)
        val savedBasis = prefs.getString("risk_basis", RiskReferenceMode.ENTRY_PRICE.name)
        basisGroup.check(if (savedBasis == RiskReferenceMode.INITIAL_CAPITAL.name) capitalRadio.id else entryRadio.id)
        outer.addView(basisGroup)
        outer.addView(infoCard(activity, "MODAL BELI PERTAMA tidak menghapus pendekatan harga entry. Ini hanya memilih referensi perhitungan TP/SL. Contoh: modal pertama Rp50.000, TP 1% = target laba Rp500 untuk coin tersebut."))

        outer.addView(label(activity, "4. TP / SL", true))
        val manualSwitch = Switch(activity).apply {
            text = "TP / SL MANUAL"
            textSize = 15f
            isChecked = prefs.getBoolean("manual_risk", false)
        }
        outer.addView(manualSwitch)
        val fields = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }
        val slField = EditText(activity).apply {
            hint = "SL %"
            setSingleLine(true)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setText(prefs.getString("manual_sl", "0.50"))
            setPadding(8, 4, 8, 4)
        }
        val tpField = EditText(activity).apply {
            hint = "TP %"
            setSingleLine(true)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setText(prefs.getString("manual_tp", "1.00"))
            setPadding(8, 4, 8, 4)
        }
        fields.addView(slField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 10 })
        fields.addView(tpField, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        outer.addView(fields)
        outer.addView(infoCard(activity, "AGGRESSIVE tetap memakai gate Mirei dan forecast. Jika TP/SL MANUAL aktif, angka di sini menjadi override; BALANCED dan SAFETY tidak diubah."))

        val dialog = AlertDialog.Builder(activity)
            .setTitle("MULAI SESI PAPER")
            .setMessage("Konfigurasi sesi sebelum runtime dimulai.")
            .setView(scroll)
            .setNegativeButton("BATAL", null)
            .setPositiveButton("MULAI", null)
            .create()

        dialog.setOnShowListener {
            dialog.window?.setLayout(
                (activity.resources.displayMetrics.widthPixels * 0.94f).toInt(),
                (activity.resources.displayMetrics.heightPixels * 0.88f).toInt()
            )
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val selected = rows.mapNotNull { (market, pair) ->
                    val (check, amount) = pair
                    if (!check.isChecked) null
                    else amount.text.toString().toDoubleOrNull()?.takeIf { it > 0.0 }?.let { market to it }
                }
                if (selected.isEmpty() || selected.size > 3) {
                    dialog.setMessage("Pilih minimal 1 dan maksimal 3 coin, dengan modal > 0.")
                    return@setOnClickListener
                }
                val total = selected.sumOf { it.second }
                if (total > 150_000.0 + 1e-6) {
                    dialog.setMessage("Total modal Rp ${numberFormat.format(total)} melebihi Rp150.000.")
                    return@setOnClickListener
                }
                val manual = manualSwitch.isChecked
                val sl = slField.text.toString().toDoubleOrNull()
                val tp = tpField.text.toString().toDoubleOrNull()
                if (manual && (sl == null || tp == null || sl <= 0.0 || tp <= sl)) {
                    dialog.setMessage("TP manual harus lebih besar dari SL manual dan keduanya harus > 0.")
                    return@setOnClickListener
                }
                val basisMode = if (basisGroup.checkedRadioButtonId == capitalRadio.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                prefs.edit()
                    .putString("mode", modeSpinner.selectedItem.toString())
                    .putBoolean("manual_risk", manual)
                    .putString("manual_sl", (sl ?: 0.50).toString())
                    .putString("manual_tp", (tp ?: 1.00).toString())
                    .putString("risk_basis", basisMode.name)
                    .apply()

                val allocations = selected.joinToString(";") { "${it.first}=${it.second}" }
                sendService(activity, MireiForegroundService.ACTION_APPLY_RISK)
                activity.window.decorView.postDelayed({
                    sendService(activity, MireiForegroundService.ACTION_START) {
                        putExtra(MireiForegroundService.EXTRA_INITIAL_ALLOCATIONS, allocations)
                        putExtra(MireiForegroundService.EXTRA_SYMBOL, selected.first().first)
                        putExtra(MireiForegroundService.EXTRA_EXCHANGE, "indodax")
                    }
                }, 180L)
                dialog.dismiss()
            }
        }
        dialog.show()
    }

    private fun sendService(activity: Activity, action: String, extras: Intent.() -> Unit = {}) {
        val intent = Intent(activity, MireiForegroundService::class.java).apply { this.action = action; extras() }
        runCatching {
            if (android.os.Build.VERSION.SDK_INT >= 26) activity.startForegroundService(intent) else activity.startService(intent)
        }
    }

    private fun label(context: Context, value: String, bold: Boolean): TextView = TextView(context).apply {
        text = value
        textSize = if (bold) 17f else 14f
        setTextColor(Color.WHITE)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        setPadding(4, 10, 4, 5)
    }

    private fun infoCard(context: Context, value: String): TextView = TextView(context).apply {
        text = value
        textSize = 13f
        setTextColor(Color.WHITE)
        setPadding(10, 10, 10, 10)
        setBackgroundColor(Color.rgb(24, 34, 43))
    }

    companion object {
        private val TAG_PATCHED = Any()
        private val TAG_OBSERVER = Any()
    }
}
