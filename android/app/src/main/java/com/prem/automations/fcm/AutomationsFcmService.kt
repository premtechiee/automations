package com.prem.automations.fcm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.getSystemService
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.prem.automations.MainActivity
import com.prem.automations.R
import javax.inject.Inject
import javax.inject.Singleton

private const val CHANNEL_ID = "automations_alerts"

class AutomationsFcmService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        // Topic-based delivery is used; token registration isn't required.
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val notif = message.notification
        val title = notif?.title ?: message.data["title"] ?: "Automations"
        val body  = notif?.body  ?: message.data["body"]  ?: "Update available"
        ensureChannel(this)
        val pi = android.app.PendingIntent.getActivity(
            this, 0,
            android.content.Intent(this, MainActivity::class.java)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP),
            android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val n = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        getSystemService<NotificationManager>()?.notify(
            (System.currentTimeMillis() % Int.MAX_VALUE).toInt(),
            n,
        )
    }
}

private fun ensureChannel(ctx: Context) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
    val nm = ctx.getSystemService<NotificationManager>() ?: return
    if (nm.getNotificationChannel(CHANNEL_ID) != null) return
    val ch = NotificationChannel(
        CHANNEL_ID,
        "Automations alerts",
        NotificationManager.IMPORTANCE_DEFAULT,
    ).apply { description = "Reports & predictions from your automations" }
    nm.createNotificationChannel(ch)
}

@Singleton
class TopicManager @Inject constructor() {
    /** Subscribe or unsubscribe from an FCM topic. Best-effort. */
    fun set(topic: String, enabled: Boolean) {
        val msg = FirebaseMessaging.getInstance()
        if (enabled) msg.subscribeToTopic(topic) else msg.unsubscribeFromTopic(topic)
    }
}
