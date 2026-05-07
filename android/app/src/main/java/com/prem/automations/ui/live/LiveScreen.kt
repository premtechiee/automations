package com.prem.automations.ui.live

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.prem.automations.data.LiveRepository
import com.prem.automations.data.api.dto.Trade
import com.prem.automations.data.api.dto.TraderState
import com.prem.automations.ui.UiState
import com.prem.automations.ui.components.StateContainer
import com.prem.automations.ui.paper.KpiHeader
import com.prem.automations.ui.safeCall
import com.prem.automations.ui.theme.PnlGreen
import com.prem.automations.ui.theme.PnlRed
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

@HiltViewModel
class LiveViewModel @Inject constructor(private val repo: LiveRepository) : ViewModel() {
    private val _state = MutableStateFlow<UiState<TraderState>>(UiState.Idle)
    val state: StateFlow<UiState<TraderState>> = _state.asStateFlow()
    init { refresh() }
    fun refresh() {
        _state.value = UiState.Loading
        viewModelScope.launch { _state.value = safeCall { repo.state() } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LiveScreen(vm: LiveViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Live trader") },
                actions = { TextButton(onClick = vm::refresh) { Text("Refresh") } },
            )
        }
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            StateContainer(state, onRetry = vm::refresh) { st ->
                Column(Modifier.fillMaxSize()) {
                    AssistChip(
                        onClick = {},
                        label = { Text("Read-only · live trading is env-gated", color = MaterialTheme.colorScheme.tertiary) },
                        modifier = Modifier.padding(12.dp),
                    )
                    KpiHeader(st)
                    HorizontalDivider()
                    Text("Open positions", modifier = Modifier.padding(12.dp), fontWeight = FontWeight.SemiBold)
                    if (st.openTrades.isEmpty()) {
                        Box(Modifier.fillMaxWidth().padding(24.dp), Alignment.Center) {
                            Text("No live positions.")
                        }
                    } else {
                        LazyColumn(
                            contentPadding = PaddingValues(12.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            items(st.openTrades, key = { it.symbol + (it.openedAt ?: "") }) { LiveTradeRow(it) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LiveTradeRow(t: Trade) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(t.symbol, fontWeight = FontWeight.SemiBold)
                Text("qty ${t.qty}")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Entry ₹%.2f".format(t.entryPrice), style = MaterialTheme.typography.bodySmall)
                Text("SL ₹%.2f".format(t.sl), style = MaterialTheme.typography.bodySmall, color = PnlRed)
                Text("Tgt ₹%.2f".format(t.target), style = MaterialTheme.typography.bodySmall, color = PnlGreen)
            }
        }
    }
}
