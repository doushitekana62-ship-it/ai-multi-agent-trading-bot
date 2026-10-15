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
import android.graphics.drawable.GradientDrawable
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.AdapterView
import android.widget.ScrollView
import android.widget.TextView
import com.mirei.app.core.PositionTradeConfigStore
import com.mirei.app.core.RiskReferenceMode
import com.mirei.app.storage.MireiDatabase
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.security.ExchangeCredentials
import com.mirei.app.security.LocalExchangeCredentialStore
import com.mirei.app.exchange.IndodaxAccountClient
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    companion object { private const val REQUEST_NOTIFICATIONS = 7001 }
    private lateinit var content: LinearLayout
    private lateinit var status: TextView
    private var activeSymbols: List<String> = emptyList()
    private var selectedMarket: String = "BTC/IDR"
    private val number = NumberFormat.getNumberInstance(Locale("id", "ID")).apply { maximumFractionDigits = 0 }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == MireiForegroundService.ACTION_STATUS) {
                if (BuildModePolicy.usesPaperRuntime(BuildConfig.MIREI_MODE)) {
                    render(intent)
                } else {
                    status.text = "MODE LIVE · EKSEKUSI TERKUNCI\n" +
                        intent.getStringExtra(MireiForegroundService.EXTRA_ERROR).orEmpty()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        PositionTradeConfigStore.reload(this)
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
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
        if (!BuildModePolicy.usesPaperRuntime(BuildConfig.MIREI_MODE)) {
            val lockedShell = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(18), dp(18), dp(18), dp(18))
                setBackgroundColor(Color.rgb(8, 18, 30))
            }
            lockedShell.addView(text("MIREI", 28f, true))
            status = card("MODE LIVE · EKSEKUSI TERKUNCI", 14f)
            lockedShell.addView(status, margin(0, 12, 0, 12))
            lockedShell.addView(text(
                "Order LIVE dinonaktifkan sampai kontrak keselamatan broker, rekonsiliasi order, dan pengelolaan posisi LIVE selesai.",
                13f,
            ))
            setContentView(lockedShell)
            return
        }

        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            setBackgroundColor(Color.rgb(8, 18, 30))
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val brand = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        brand.addView(text("MIREI", 27f, true))
        brand.addView(text("PAPER TRADING  ·  SIMULASI", 10f).apply { setTextColor(Color.rgb(73, 205, 190)) })
        header.addView(brand, LinearLayout.LayoutParams(0, -2, 1f))
        header.addView(text("●  PAPER", 11f, true).apply { setTextColor(Color.rgb(73, 205, 190)) })
        shell.addView(header, margin(0, 0, 0, 12))

        val controls = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row1.addView(button("▶  MULAI") {
            if (isRiskConfigured()) {
                status.text = "MENYIAPKAN SESI…"
                MireiStartSessionDialog.show(this@MainActivity) { status.text = "MENYIAPKAN SESI…" }
            } else showRiskRequired()
        }, gridParams())
        row1.addView(button("Ⅱ  STOP") { showStopDialog() }, gridParams())
        row1.addView(button("▶  LANJUTKAN") { send(MireiForegroundService.ACTION_RESUME) }, gridParams())
        row2.addView(button("TUTUP SEMUA") {
            AlertDialog.Builder(this@MainActivity)
                .setTitle("Tutup semua posisi?")
                .setMessage("Semua posisi PAPER yang terbuka akan ditutup dan hasilnya dicatat ke riwayat.")
                .setNegativeButton("Batal", null)
                .setPositiveButton("Tutup Semua") { _, _ -> send(MireiForegroundService.ACTION_CLOSE_ALL) }
                .show()
        }, gridParams())
        row2.addView(button("ATUR SL/TP") { showRiskDialog() }, gridParams())
        row2.addView(button("RESET") { confirmReset() }, gridParams())
        controls.addView(row1)
        controls.addView(row2)
        shell.addView(controls)

        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(10), 0, dp(12))
        }
        status = card("Status sedang dimuat…", 14f)
        content.addView(status, margin(0, 0, 0, 12))
        val scroll = ScrollView(this).apply {
            isFillViewport = false
            clipToPadding = false
            addView(content, ViewGroup.LayoutParams(-1, -2))
        }
        shell.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        val link = TextView(this).apply {
            text = "⚙  TAUTKAN EXCHANGE / API"
            textSize = 12f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(224, 235, 245))
            isClickable = true
            isFocusable = true
            background = rounded(Color.rgb(22, 38, 55), dp(10))
            setPadding(0, dp(12), 0, dp(12))
            setOnClickListener { linkExchanges() }
        }
        shell.addView(link, margin(0, 8, 0, 0))
        setContentView(shell)
    }

    private fun rounded(color: Int, radius: Int = dp(12)): GradientDrawable =
        GradientDrawable().apply { setColor(color); cornerRadius = radius.toFloat() }

    private fun addLinkButton(shell: LinearLayout) {
        shell.addView(card("TAUTKAN\nExchange : INDODAX, BYBIT, STOCKBIT, BINANCE, ETC.\nAPI KEYS : -\nStatus Broker ter taut : belum ada\nMode Live : dipersiapkan, trading live tetap terkunci sampai API pairing + adapter siap.", 11.5f))
        val link = TextView(this).apply {
            text = "TAUTKAN EXCHANGE"
            textSize = 13f
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(35,35,35))
            isClickable = true
            isFocusable = true
            background = GradientDrawable().apply { setColor(Color.rgb(252,229,154)); cornerRadius = 12f }
            setOnClickListener { linkExchanges() }
        }
        shell.addView(link, LinearLayout.LayoutParams(-1, 48).apply { setMargins(3, 3, 3, 3) })
    }
    private fun addMarketSection(intent: Intent) {
        val markets = com.mirei.app.core.TradingUniverse.byClass(com.mirei.app.core.AssetClass.CRYPTO).map { it.symbol }
        val saved = getSharedPreferences("mirei_settings", MODE_PRIVATE).getString("selected_market", null)
        selectedMarket = saved?.takeIf { it in markets } ?: intent.getStringExtra(MireiForegroundService.EXTRA_SELECTED_MARKET)?.takeIf { it in markets } ?: markets.firstOrNull().orEmpty()
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = rounded(Color.rgb(18, 32, 47), dp(12))
        }
        box.addView(text("COIN UTAMA  ·  MARKET YANG DIPANTAU", 10.5f, true).apply { setTextColor(Color.rgb(150, 174, 196)) })
        val spinner = Spinner(this)
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, markets)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinner.adapter = adapter
        spinner.setSelection(markets.indexOf(selectedMarket).coerceAtLeast(0), false)
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val chosen = markets.getOrNull(position) ?: return
                if (chosen == selectedMarket) return
                selectedMarket = chosen
                getSharedPreferences("mirei_settings", MODE_PRIVATE).edit().putString("selected_market", chosen).apply()
                selectMarket(chosen)
            }
        }
        box.addView(spinner, LinearLayout.LayoutParams(-1, 48))
        val runtimeSymbol = intent.getStringExtra(MireiForegroundService.EXTRA_SYMBOL).orEmpty()
        val price = intent.getDoubleExtra(MireiForegroundService.EXTRA_PRICE, 0.0)
        val fresh = intent.getBooleanExtra(MireiForegroundService.EXTRA_MARKET_FRESH, false)
        val pulse = if (runtimeSymbol == selectedMarket && price > 0.0) {
            "Market Pulse : $runtimeSymbol · Rp ${number.format(price)} · ${if (fresh) "DATA SEGAR" else "DATA LAMA"}"
        } else {
            "Market Pulse : $selectedMarket · belum menjadi market runtime aktif"
        }
        box.addView(text(pulse, 12f, true).apply {
            setTextColor(if (runtimeSymbol == selectedMarket && price > 0.0 && fresh) Color.rgb(73, 205, 190) else Color.rgb(235, 183, 93))
        }, margin(0, 6, 0, 2))
        box.addView(text("Pilihan coin disimpan di perangkat. Data pasar akan ditandai segar hanya jika sumber data mengonfirmasikannya.", 10f).apply { setTextColor(Color.rgb(150, 174, 196)) })
        content.addView(box, margin(0, 0, 0, 8))
    }
    private fun render(intent: Intent) {
        val stateValue = intent.getStringExtra(MireiForegroundService.EXTRA_STATE) ?: "STOP"
        val balance = intent.getDoubleExtra(MireiForegroundService.EXTRA_BALANCE, 0.0)
        val equity = intent.getDoubleExtra(MireiForegroundService.EXTRA_EQUITY, 0.0)
        val winRate = intent.getDoubleExtra(MireiForegroundService.EXTRA_WIN_RATE, 0.0)
        val tpWins = intent.getIntExtra(MireiForegroundService.EXTRA_TP_WINS, 0)
        val closedTrades = intent.getIntExtra(MireiForegroundService.EXTRA_CLOSED_TRADES, 0)
        val totalReentries = intent.getIntExtra(MireiForegroundService.EXTRA_TOTAL_REENTRIES, 0)
        val lastTick = intent.getLongExtra(MireiForegroundService.EXTRA_LAST_TICK, 0L)
        val tickAgeSec = if (lastTick > 0L) ((System.currentTimeMillis() - lastTick).coerceAtLeast(0L) / 1000L) else -1L
        val stateLabel = when {
            stateValue == "RUNNING" && tickAgeSec in 0..15 -> "BOT BERJALAN  ·  tick ${tickAgeSec}d lalu"
            stateValue == "RUNNING" -> "TICK TERLAMBAT  ·  ${tickAgeSec}d"
            stateValue == "HOLD_OFFLINE" -> "MENUNGGU INTERNET"
            stateValue == "HOLD" -> "DIJEDA"
            else -> "BERHENTI"
        }
        val error = intent.getStringExtra(MireiForegroundService.EXTRA_ERROR).orEmpty()
        val rows = intent.getStringExtra(MireiForegroundService.EXTRA_POSITIONS_DETAIL).orEmpty()
            .lines().filter { it.isNotBlank() }
        activeSymbols = rows.mapNotNull { it.split("|").firstOrNull()?.takeIf { symbol -> symbol.isNotBlank() } }

        content.removeAllViews()
        val stateColor = when (stateValue) {
            "RUNNING" -> Color.rgb(11, 104, 84)
            "HOLD_OFFLINE" -> Color.rgb(130, 78, 18)
            "HOLD" -> Color.rgb(38, 65, 93)
            else -> Color.rgb(39, 50, 66)
        }
        content.addView(card("●  $stateLabel\nKas tersedia     Rp ${number.format(balance)}\nEquity             Rp ${number.format(equity)}", 14f).apply {
            setTextColor(Color.WHITE)
            background = rounded(stateColor, dp(12))
        }, margin(0, 0, 0, 12))
        if (error.isNotBlank()) {
            content.addView(card("Perlu perhatian\n$error", 12f), margin(0, 0, 0, 10))
        }

        addSection("PASAR AKTIF")
        addMarketSection(intent)
        addSection("POSISI AKTIF  ·  ${rows.size}/10")
        if (rows.isEmpty()) {
            content.addView(card("Belum ada posisi terbuka.\nMulai sesi PAPER setelah memeriksa konfigurasi SL/TP.", 13f), margin(0, 0, 0, 10))
        } else {
            rows.forEach { row ->
                val p = row.split('|')
                if (p.size >= 5) {
                    val symbol = p[0]
                    val stake = p.getOrNull(1)?.toDoubleOrNull() ?: 0.0
                    val entry = p.getOrNull(2)?.toDoubleOrNull() ?: 0.0
                    val sl = p.getOrNull(3)?.toDoubleOrNull() ?: 0.0
                    val tp = p.getOrNull(4)?.toDoubleOrNull() ?: 0.0
                    val pnl = p.getOrNull(5)?.toDoubleOrNull() ?: 0.0
                    val mark = p.getOrNull(8)?.toDoubleOrNull() ?: entry
                    val trend = p.getOrNull(9) ?: "FLAT"
                    val cycle = p.getOrNull(11) ?: "HOLDING"
                    val pnlColor = if (pnl >= 0) Color.rgb(24, 164, 123) else Color.rgb(213, 73, 83)
                    val position = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL
                        setPadding(dp(14), dp(12), dp(14), dp(12))
                        background = rounded(Color.rgb(18, 32, 47), dp(12))
                    }
                    val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                    top.addView(text(symbol, 15f, true), LinearLayout.LayoutParams(0, -2, 1f))
                    top.addView(text(trend, 10f, true).apply { setTextColor(Color.rgb(73, 205, 190)) })
                    position.addView(top)
                    position.addView(text("Entry  Rp ${number.format(entry)}    Harga  Rp ${number.format(mark)}", 11f).apply { setTextColor(Color.rgb(180, 197, 214)) }, margin(0, 5, 0, 2))
                    position.addView(text("Modal  Rp ${number.format(stake)}    PnL bersih  Rp ${number.format(pnl)}", 12f, true).apply { setTextColor(pnlColor) }, margin(0, 3, 0, 2))
                    position.addView(text("SL ${if (sl > 0) "Rp " + number.format(sl) else "OFF"}   ·   TP Rp ${number.format(tp)}   ·   $cycle", 10.5f).apply { setTextColor(Color.rgb(180, 197, 214)) }, margin(0, 3, 0, 0))
                    content.addView(position, margin(0, 0, 0, 8))
                }
            }
        }

        addSection("STATISTIK")
        val statGrid = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        statGrid.addView(metricCard("WIN RATE TP", String.format(Locale.US, "%.1f%%", winRate), "$tpWins dari $closedTrades trade"), LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = dp(4) })
        statGrid.addView(metricCard("TRADE SELESAI", closedTrades.toString(), "$totalReentries re-entry"), LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = dp(4) })
        content.addView(statGrid, margin(0, 0, 0, 10))

        renderHistoryTable()
    }

    private fun metricCard(label: String, value: String, caption: String): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = rounded(Color.rgb(18, 32, 47), dp(12))
            addView(text(label, 9.5f, true).apply { setTextColor(Color.rgb(150, 174, 196)) })
            addView(text(value, 22f, true).apply { setTextColor(Color.WHITE) }, margin(0, 5, 0, 2))
            addView(text(caption, 10f).apply { setTextColor(Color.rgb(73, 205, 190)) })
        }

    private fun renderHistoryTable() {
        val database = MireiDatabase(this)
        val rows = database.recentTrades(100)
        val metrics = database.performanceMetrics()
        addSection("STATISTIK")
        content.addView(card(
            "Win Rate TP : " + String.format(Locale.US, "%.1f%%", metrics.winRatePercent) +
                "  ·  TP berhasil : " + metrics.tpWins +
                "  ·  Trade selesai : " + metrics.closedTrades +
                "  ·  Total re-entry : " + metrics.totalReentries,
            11.5f
        ))
        addSection("AKTIVITAS TERAKHIR")
        val audits = database.recentAudit(5)
        audits.forEach { audit ->
            val friendly = when (audit.eventType) {
                "TRADE_CLOSE" -> "Trade ditutup"
                "TP_SELL" -> "Take Profit tercapai"
                "SL_SELL" -> "Stop Loss tercapai"
                "RE_ENTRY_BUY" -> "Re-entry dilakukan"
                "INITIAL_BUY" -> "Posisi awal dibuat"
                "SESSION_STOPPED" -> "Bot dihentikan"
                "POSITIONS_RESUMED" -> "Sesi dilanjutkan"
                "CLOSE_ALL_REQUESTED" -> "Permintaan tutup semua"
                "CLOSE_ALL_COMPLETED" -> "Semua posisi sudah ditutup"
                "CLOSE_ALL_INCOMPLETE" -> "Masih ada posisi terbuka"
                "CLOSE_ALL_FAILED" -> "Gagal menutup semua posisi"
                "RUNTIME_TICK_FAILED" -> "Runtime mengalami error"
                "MARKET_SELECTED" -> "Coin pilihan diperbarui"
                else -> audit.eventType.replace('_', ' ').lowercase().replaceFirstChar { it.uppercase() }
            }
            val detail = when (audit.eventType) {
                "TRADE_CLOSE" -> audit.details.split('|').filter { it.startsWith("symbol=") || it.startsWith("pnl=") || it.startsWith("exit_reason=") }
                    .joinToString(" · ") { it.substringAfter('=') }
                "CLOSE_ALL_INCOMPLETE" -> audit.details.substringAfter("remaining_positions=", audit.details)
                    .let { "Sisa posisi: $it" }
                "CLOSE_ALL_FAILED", "RUNTIME_TICK_FAILED" -> audit.details.take(120)
                "MARKET_SELECTED" -> audit.details.substringAfter("symbol=", audit.details).substringBefore('|')
                else -> ""
            }
            content.addView(card(
                formatTime(audit.createdAtEpochMs) + "  ·  " + friendly +
                    if (detail.isNotBlank()) "\n" + detail else "",
                11f
            ), margin(0, 0, 0, 6))
        }
        if (audits.isEmpty()) content.addView(card("Belum ada aktivitas runtime.", 11f))
        addSection("HISTORY")
        val table = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            minimumWidth = dp(780)
        }
        table.addView(tableRow(listOf("WAKTU", "JENIS TRADE", "SIKLUS / STATUS", "ENTRY", "MODAL AWAL", "PnL"), true))
        rows.forEach { row ->
            val asset = com.mirei.app.core.TradingUniverse.bySymbol(row.symbol)?.assetClass?.label ?: row.symbol
            val statusLabel = when {
                row.entryReason == "re_entry" && row.exitReason == "take_profit" -> "RE-ENTRY / TP"
                row.entryReason == "re_entry" && row.exitReason == "stop_loss" -> "RE-ENTRY / SL"
                row.entryReason == "re_entry" && row.status == "OPEN" -> "RE-ENTRY / OPEN"
                row.exitReason == "take_profit" -> "TP"
                row.exitReason == "stop_loss" -> "SL"
                row.exitReason == "manual_close_all" -> "CLOSED / MANUAL"
                row.exitReason == "manual_stop" -> "CLOSED / STOP"
                row.status == "OPEN" -> "OPEN"
                else -> "CLOSED"
            }
            table.addView(tableRow(listOf(
                formatTime(row.closedAtEpochMs ?: row.openedAtEpochMs),
                asset + " (" + row.symbol + ")",
                statusLabel,
                row.entryPrice?.let { number.format(it) } ?: "-",
                number.format(row.stakeIdr),
                number.format(row.pnlIdr),
            ), false))
        }
        if (rows.isEmpty()) table.addView(text("Belum ada history.", 12f))
        content.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = true
            isFillViewport = false
            addView(table, ViewGroup.LayoutParams(dp(880), ViewGroup.LayoutParams.WRAP_CONTENT))
        })
    }
    private fun showRiskDialog() {
        val current = PositionTradeConfigStore.snapshot()["*"]
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 4, 12, 4) }
        val sl = EditText(this).apply { hint = "SL % (0 = OFF)"; setSingleLine(true); setText((current?.stopLossPercent ?: 0.0).toString()) }
        val tp = EditText(this).apply { hint = "TP bersih Rp"; setSingleLine(true); setText((current?.manualNetProfitTargetIdr ?: 30.0).toString()) }
        val basis = RadioGroup(this).apply { orientation = RadioGroup.VERTICAL }
        val entry = RadioButton(this).apply { id = View.generateViewId(); text = "Harga entry" }
        val initial = RadioButton(this).apply { id = View.generateViewId(); text = "Modal pertama" }
        basis.addView(entry); basis.addView(initial)
        basis.check(if (current?.riskReferenceMode == RiskReferenceMode.INITIAL_CAPITAL) initial.id else entry.id)
        box.addView(text("SL / TP manual", 15f, true))
        box.addView(text("SL = persen atau OFF. TP = target bersih setelah biaya.", 12f))
        box.addView(sl); box.addView(tp); box.addView(basis)
        box.addView(text("Fee calc = target TP bersih setelah fee; fee mengikuti exchange/instrument.", 11f))
        val dialog = AlertDialog.Builder(this)
            .setTitle("ATUR SL/TP")
            .setView(box)
            .setNegativeButton("BATAL", null)
            .setNeutralButton("ATUR DEFAULT", null)
            .setPositiveButton("SIMPAN", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener {
                sl.setText("0.0"); tp.setText("30"); basis.check(entry.id)
            }
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val slValue = sl.text.toString().toDoubleOrNull()
                val tpValue = tp.text.toString().toDoubleOrNull()
                if (slValue == null || slValue < 0.0 || tpValue == null || tpValue <= 0.0) { box.addView(text("SL/TP tidak valid", 11f)); return@setOnClickListener }
                val ref = if (basis.checkedRadioButtonId == initial.id) RiskReferenceMode.INITIAL_CAPITAL else RiskReferenceMode.ENTRY_PRICE
                getSharedPreferences("mirei_settings", MODE_PRIVATE).edit().putString("position_profiles", "*|" + slValue + "," + tpValue + "," + ref.name).putBoolean("sl_tp_configured", true).apply()
                PositionTradeConfigStore.reload(this)
                send(MireiForegroundService.ACTION_APPLY_RISK)
                dialog.dismiss()
            }
        }
        dialog.show()
    }
    private fun showStopDialog() {
        val active = activeSymbols
        if (active.isEmpty()) { AlertDialog.Builder(this).setTitle("STOP POSISI").setMessage("Tidak ada posisi aktif.").setPositiveButton("OK", null).show(); return }
        val labels = active.toTypedArray()
        val checked = BooleanArray(labels.size)
        AlertDialog.Builder(this).setTitle("STOP POSISI")
            .setMultiChoiceItems(labels, checked) { _, which, isChecked -> checked[which] = isChecked }
            .setNegativeButton("BATAL", null)
            .setNeutralButton("STOP SEMUA") { _, _ -> send(MireiForegroundService.ACTION_STOP_SELECTED, labels.toList()) }
            .setPositiveButton("STOP TERPILIH") { _, _ ->
                val selected = labels.filterIndexed { index, _ -> checked[index] }
                if (selected.isNotEmpty()) send(MireiForegroundService.ACTION_STOP_SELECTED, selected)
            }.show()
    }

    private fun linkExchanges() {
        val existing = LocalExchangeCredentialStore.load(this)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(12, 4, 12, 4) }
        val key = EditText(this).apply {
            hint = "INDODAX API KEY"
            setSingleLine(true)
            setText(existing?.apiKey.orEmpty())
        }
        val secret = EditText(this).apply {
            hint = "INDODAX API SECRET"
            setSingleLine(true)
            inputType = 0x00000081
        }
        box.addView(text("INDODAX · credential hanya disimpan lokal di Android.", 12f))
        box.addView(key)
        box.addView(secret)
        box.addView(text(
            if (existing != null) "Status: credential lokal tersimpan." else "Status: belum terhubung.",
            12f
        ))
        box.addView(text("Tidak ada API key/secret/ENV yang ditanam di repository.", 11f))
        val dialog = AlertDialog.Builder(this)
            .setTitle("TAUTKAN INDODAX")
            .setView(box)
            .setNegativeButton("BATAL", null)
            .setNeutralButton("TES BACA KAS", null)
            .setPositiveButton("SIMPAN LOKAL", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val apiKey = key.text.toString().trim()
                val apiSecret = secret.text.toString()
                if (apiKey.isBlank() || apiSecret.isBlank()) {
                    box.addView(text("API KEY dan API SECRET wajib diisi.", 11f))
                    return@setOnClickListener
                }
                LocalExchangeCredentialStore.save(this, ExchangeCredentials("indodax", apiKey, apiSecret))
                box.addView(text("Tersimpan lokal di Android. Secret tidak ditampilkan kembali.", 11f))
            }
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener {
                val apiKey = key.text.toString().trim()
                val apiSecret = secret.text.toString()
                if (apiKey.isBlank() || apiSecret.isBlank()) {
                    box.addView(text("Isi API KEY dan API SECRET terlebih dahulu.", 11f))
                    return@setOnClickListener
                }
                Thread {
                    val result = runCatching {
                        IndodaxAccountClient(ExchangeCredentials("indodax", apiKey, apiSecret)).getInfo()
                    }
                    runOnUiThread {
                        result.onSuccess {
                            LocalExchangeCredentialStore.save(this, ExchangeCredentials("indodax", apiKey, apiSecret))
                            box.addView(text(
                                "TERHUBUNG · Kas IDR aktif: Rp " + number.format(it.idrAvailable) +
                                    " · Hold: Rp " + number.format(it.idrHold),
                                11f
                            ))
                        }.onFailure {
                            box.addView(text("GAGAL BACA KAS: " + (it.message ?: "unknown_error"), 11f))
                        }
                    }
                }.start()
            }
        }
        dialog.show()
    }

    private fun gridParams(): LinearLayout.LayoutParams = LinearLayout.LayoutParams(0, 48).apply { weight = 1f; setMargins(3, 3, 3, 3) }
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

    private fun selectMarket(symbol: String) {
        val intent = Intent(this, MireiForegroundService::class.java).apply {
            action = MireiForegroundService.ACTION_SELECT_MARKET
            putExtra(MireiForegroundService.EXTRA_SELECTED_MARKET, symbol)
        }
        runCatching { if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }
    }
    private fun send(action: String, symbols: List<String> = emptyList()) {
        val intent = Intent(this, MireiForegroundService::class.java).apply {
            this.action = action
            if (symbols.isNotEmpty()) putStringArrayListExtra(MireiForegroundService.EXTRA_SELECTED_SYMBOLS, ArrayList(symbols))
        }
        runCatching { if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }
    }
    private fun addSection(title: String) {
        content.addView(text(title, 15f, true).apply {
            setTextColor(Color.WHITE)
            setPadding(dp(2), dp(10), dp(2), dp(4))
        }, margin(0, 8, 0, 4))
    }

    private fun tableRow(values: List<String>, header: Boolean): View {
        val widthsDp = intArrayOf(145, 185, 155, 150, 135, 110)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; minimumWidth = dp(widthsDp.sum()) }
        values.forEachIndexed { index, value ->
            val cell = text(value, if (header) 10f else 9.5f, header).apply {
                setTextColor(if (header) Color.rgb(35, 35, 35) else Color.WHITE)
                setPadding(dp(8), dp(6), dp(8), dp(6))
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                setBackgroundColor(if (header) Color.rgb(248, 249, 250) else Color.rgb(30, 70, 82))
                setMinHeight(dp(44))
            }
            row.addView(cell, LinearLayout.LayoutParams(dp(widthsDp.getOrElse(index) { 100 }), dp(44)))
        }
        return row
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun button(label: String, action: () -> Unit): TextView = TextView(this).apply {
        text = label
        textSize = 10.5f
        gravity = Gravity.CENTER
        setTextColor(Color.WHITE)
        isClickable = true
        isFocusable = true
        background = GradientDrawable().apply {
            val fill = when {
                label.contains("MULAI") -> Color.rgb(10, 157, 116)
                label.contains("STOP") || label.contains("TUTUP") -> Color.rgb(194, 55, 67)
                label.contains("LANJUTKAN") -> Color.rgb(22, 137, 220)
                else -> Color.rgb(29, 48, 68)
            }
            setColor(fill)
            cornerRadius = dp(10).toFloat()
        }
        setOnClickListener { action() }
    }

    private fun card(value: String, size: Float = 13f): TextView = text(value, size).apply {
        setPadding(dp(14), dp(12), dp(14), dp(12))
        setTextColor(Color.rgb(28, 48, 56))
        setLineSpacing(dp(2).toFloat(), 1.0f)
        setBackground(GradientDrawable().apply {
            setColor(Color.rgb(238, 245, 247))
            cornerRadius = dp(10).toFloat()
        })
    }

    private fun text(value: String, size: Float, bold: Boolean = false): TextView = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(Color.WHITE)
        setLineSpacing(dp(1).toFloat(), 1.0f)
        gravity = Gravity.START
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun margin(l: Int, t: Int, r: Int, b: Int): ViewGroup.MarginLayoutParams =
        ViewGroup.MarginLayoutParams(-1, -2).apply { leftMargin = l; topMargin = t; rightMargin = r; bottomMargin = b }

    private fun formatTime(epoch: Long): String =
        SimpleDateFormat("dd/MM HH:mm:ss", Locale.US).format(Date(epoch))
}
