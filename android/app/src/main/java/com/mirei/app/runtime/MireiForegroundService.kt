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
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate() {
        super.onCreate()
        try {
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Mirei Runtime",
                    NotificationManager.IMPORTANCE_LOW,
                )
            )

            val connectivity = getSystemService(ConnectivityManager::class.java)
            connectivityManager = connectivity
            val callback = object : ConnectivityManager.NetworkCallback() {
                override fun onLost(network: Network) {
                    runCatching {
                        controller.onNetworkLost()
                        publish("Internet lost — Mirei HOLD")
                    }.onFailure { handleRuntimeFailure("Network monitor failed", it) }
                }
            }
            networkCallback = callback
            connectivity.registerDefaultNetworkCallback(callback)
        } catch (error: Exception) {
            handleRuntimeFailure("Mirei initialization failed", error)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
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
        } catch (error: Exception) {
            handleRuntimeFailure("Mirei action failed", error)
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        try {
            networkCallback?.let { connectivityManager?.unregisterNetworkCallback(it) }
        } catch (_: Exception) {
            // Cleanup must never crash the service during teardown.
        } finally {
            networkCallback = null
            connectivityManager = null
        }
        super.onDestroy()
    }

    private fun handleRuntimeFailure(message: String, error: Throwable) {
        controller.onEngineError()
        runCatching { publish("$message — Mirei STOP") }
        stopSelf()
    }

    private fun publish(text: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, notification(text))
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
