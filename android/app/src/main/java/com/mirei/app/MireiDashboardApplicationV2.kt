package com.mirei.app

import android.app.Application
import com.mirei.app.core.PositionTradeConfigStore

class MireiDashboardApplicationV2 : Application() {
    override fun onCreate() {
        super.onCreate()
        PositionTradeConfigStore.reload(this)
    }
}
