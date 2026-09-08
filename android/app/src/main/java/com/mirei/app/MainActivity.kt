package com.mirei.app

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import com.mirei.app.runtime.MireiForegroundService

class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 40, 32, 32)
        }

        root.addView(TextView(this).apply {
            text = "Mirei ミレイ"
            textSize = 30f
        }, LinearLayout.LayoutParams(MATCH_PARENT, -2))

        root.addView(TextView(this).apply {
            text = "Android-first trading runtime"
            textSize = 16f
        }, LinearLayout.LayoutParams(MATCH_PARENT, -2))

        status = TextView(this).apply {
            text = "\nState: STOP\nMode: Suggestion\nPaper trading: SAFE DEFAULT"
            textSize = 18f
        }
        root.addView(status, LinearLayout.LayoutParams(MATCH_PARENT, -2))

        root.addView(actionButton("START") { sendAction(MireiForegroundService.ACTION_START, "RUNNING") })
        root.addView(actionButton("HOLD") { sendAction(MireiForegroundService.ACTION_HOLD, "HOLD") })
        root.addView(actionButton("STOP") { sendAction(MireiForegroundService.ACTION_STOP, "STOP") })
        root.addView(actionButton("CLOSE ALL") { sendAction(MireiForegroundService.ACTION_CLOSE_ALL, "CLOSE_ALL") })

        setContentView(root)
    }

    private fun actionButton(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        setOnClickListener { action() }
    }

    private fun sendAction(command: String, nextState: String) {
        try {
            val intent = Intent(this, MireiForegroundService::class.java).setAction(command)
            if (command == MireiForegroundService.ACTION_START && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            status.text = "\nState: $nextState\nMode: Suggestion\nPaper trading: SAFE DEFAULT"
        } catch (error: Exception) {
            status.text = "\nState: ERROR\nMode: Suggestion\nPaper trading: SAFE DEFAULT\nService error: ${error.javaClass.simpleName}"
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST_NOTIFICATIONS)
        }
    }

    companion object {
        private const val REQUEST_NOTIFICATIONS = 2001
    }
}
