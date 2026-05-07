package com.prem.automations.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "automations_settings")

private val KEY_BASE_URL = stringPreferencesKey("base_url")
private val KEY_TOKEN = stringPreferencesKey("token")
private val KEY_TOPIC_STOCK = booleanPreferencesKey("topic_stock")
private val KEY_TOPIC_GOLD  = booleanPreferencesKey("topic_gold")
private val KEY_TOPIC_PAPER = booleanPreferencesKey("topic_paper")
private val KEY_TOPIC_LIVE  = booleanPreferencesKey("topic_live")

data class Settings(
    val baseUrl: String,
    val token: String,
    val topicStock: Boolean = true,
    val topicGold: Boolean = true,
    val topicPaper: Boolean = true,
    val topicLive: Boolean = true,
) {
    val configured: Boolean get() = baseUrl.isNotBlank() && token.isNotBlank()
}

@Singleton
class SettingsStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val flow: Flow<Settings> = context.dataStore.data.map { p ->
        Settings(
            baseUrl    = p[KEY_BASE_URL].orEmpty(),
            token      = p[KEY_TOKEN].orEmpty(),
            topicStock = p[KEY_TOPIC_STOCK] ?: true,
            topicGold  = p[KEY_TOPIC_GOLD]  ?: true,
            topicPaper = p[KEY_TOPIC_PAPER] ?: true,
            topicLive  = p[KEY_TOPIC_LIVE]  ?: true,
        )
    }

    suspend fun current(): Settings = flow.first()

    suspend fun update(baseUrl: String, token: String) {
        context.dataStore.edit { p ->
            p[KEY_BASE_URL] = baseUrl.trim().trimEnd('/')
            p[KEY_TOKEN] = token.trim()
        }
    }

    suspend fun setTopic(topic: String, enabled: Boolean) {
        val key = when (topic) {
            "stock_reports" -> KEY_TOPIC_STOCK
            "gold_updates"  -> KEY_TOPIC_GOLD
            "paper_reports" -> KEY_TOPIC_PAPER
            "live_alerts"   -> KEY_TOPIC_LIVE
            else -> return
        }
        context.dataStore.edit { p -> p[key] = enabled }
    }
}
