package com.mirei.app

import android.content.Intent
import android.os.Build
import android.app.Application
import com.mirei.app.core.PositionTradeConfigStore
import com.mirei.app.runtime.MireiForegroundService
import com.mirei.app.storage.PaperSessionStore

class MireiDashboardApplicationV2 : Application() {
    override fun onCreate() {
        super.onCreate()
        PositionTradeConfigStore.reload(this)
        val saved = runCatching { PaperSessionStore(this).load() }.getOrNull()
        if (saved?.active == true && saved.runStoppedAtEpochMs == 0L) {
            val intent = Intent(this, MireiForegroundService::class.java).apply { action = MireiForegroundService.ACTION_START }
            runCatching { if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent) }
        }
    }
}
