package com.mirei.app.runtime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.os.IBinder
import com.mirei.app.core.MireiState

class MireiForegroundService : Service() {
    private val controller = MireiRuntimeController()
    private lateinit var connectivityManager: ConnectivityManager
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Mirei Runtime",
                NotificationManager.IMPORTANCE_LOW,
            )
        )
        connectivityManager = getSystemService(ConnectivityManager::class.java)
        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onLost(network: Network) {
                controller.onNetworkLost()
                publish("Internet lost — Mirei HOLD")
            }
        }
        connectivityManager.registerDefaultNetworkCallback(networkCallback!!)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, notification("Mirei ${controller.state.name}"))
        when (intent?.action) {
            ACTION_START -> controller.start()
            ACTION_HOLD -> controller.hold()
            ACTION_STOP -> controller.stop()
            ACTION_CLOSE_ALL -> controller.closeAll()
        }
        publish("Mirei ${controller.state.name}")
        if (controller.state == MireiState.STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        networkCallback?.let { connectivityManager.unregisterNetworkCallback(it) }
        networkCallback = null
        super.onDestroy()
    }

    private fun publish(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification = Notification.Builder(this, CHANNEL_ID)
        .setContentTitle("Mirei ミレイ")
        .setContentText(text)
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setOngoing(controller.state != MireiState.STOP)
        .build()

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_START = "com.mirei.app.action.START"
        const val ACTION_HOLD = "com.mirei.app.action.HOLD"
        const val ACTION_STOP = "com.mirei.app.action.STOP"
        const val ACTION_CLOSE_ALL = "com.mirei.app.action.CLOSE_ALL"
        private const val CHANNEL_ID = "mirei_runtime"
        private const val NOTIFICATION_ID = 1001
    }
}
