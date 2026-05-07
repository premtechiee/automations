package com.prem.automations

import android.app.Application
import com.prem.automations.data.SettingsStore
import com.prem.automations.fcm.TopicManager
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

@HiltAndroidApp
class AutomationsApp : Application() {
    @Inject lateinit var settings: SettingsStore
    @Inject lateinit var topics: TopicManager

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        // Reconcile FCM topic subscriptions with the user's saved preferences.
        scope.launch {
            val s = settings.current()
            runCatching { topics.set("stock_reports", s.topicStock) }
            runCatching { topics.set("gold_updates",  s.topicGold)  }
            runCatching { topics.set("paper_reports", s.topicPaper) }
            runCatching { topics.set("live_alerts",   s.topicLive)  }
        }
    }
}
