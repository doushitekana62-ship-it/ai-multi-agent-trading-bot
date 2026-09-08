package com.mirei.app

import android.app.Activity
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }
        root.addView(TextView(this).apply {
            text = "Mirei ミレイ"
            textSize = 28f
        })
        root.addView(TextView(this).apply {
            text = "Android-first trading runtime — MVP shell"
            textSize = 16f
        })
        root.addView(TextView(this).apply {
            text = "\nStatus: STOP\nMode: Suggestion\nPaper trading: available in next implementation stage"
            textSize = 18f
        })
        setContentView(root)
    }
}
