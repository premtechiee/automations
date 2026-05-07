package com.prem.automations.ui.settings

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.prem.automations.data.Settings
import com.prem.automations.data.SettingsStore
import com.prem.automations.fcm.TopicManager
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val store: SettingsStore,
    private val topics: TopicManager,
) : ViewModel() {
    val current: StateFlow<Settings> = store.flow
        .stateIn(viewModelScope, SharingStarted.Eagerly, Settings("", ""))

    fun save(baseUrl: String, token: String) {
        viewModelScope.launch { store.update(baseUrl, token) }
    }

    fun setTopic(name: String, enabled: Boolean) {
        viewModelScope.launch {
            store.setTopic(name, enabled)
            runCatching { topics.set(name, enabled) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: SettingsViewModel = hiltViewModel()) {
    val saved by vm.current.collectAsState()
    var baseUrl by rememberSaveable(saved.baseUrl) { mutableStateOf(saved.baseUrl) }
    var token by rememberSaveable(saved.token) { mutableStateOf(saved.token) }
    var snack by remember { mutableStateOf<String?>(null) }
    val snackHost = remember { SnackbarHostState() }

    LaunchedEffect(snack) {
        snack?.let { snackHost.showSnackbar(it); snack = null }
    }

    val notifPerm = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* result ignored — toggles still work, OS just won't display */ }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Settings") }) },
        snackbarHost = { SnackbarHost(snackHost) },
    ) { padding ->
        Column(
            Modifier.padding(padding).padding(16.dp).fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Connect to your automations API.", style = MaterialTheme.typography.bodyMedium)
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                label = { Text("Base URL (e.g. https://yourname.pythonanywhere.com)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("Bearer token (APP_API_TOKEN)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = {
                    vm.save(baseUrl, token)
                    snack = "Saved."
                },
                modifier = Modifier.align(Alignment.End),
            ) { Text("Save") }
            HorizontalDivider()
            Text("Push notifications", style = MaterialTheme.typography.titleMedium)
            TopicToggle("Stock reports", "stock_reports", saved.topicStock, vm::setTopic) {
                if (Build.VERSION.SDK_INT >= 33) notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            TopicToggle("Gold updates",  "gold_updates",  saved.topicGold,  vm::setTopic) {}
            TopicToggle("Paper reports", "paper_reports", saved.topicPaper, vm::setTopic) {}
            TopicToggle("Live alerts",   "live_alerts",   saved.topicLive,  vm::setTopic) {}
            HorizontalDivider()
            Text("App version 0.1.0", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun TopicToggle(
    label: String,
    topic: String,
    enabled: Boolean,
    onChange: (String, Boolean) -> Unit,
    onFirstEnable: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label)
        Switch(
            checked = enabled,
            onCheckedChange = { on ->
                if (on) onFirstEnable()
                onChange(topic, on)
            },
        )
    }
}
