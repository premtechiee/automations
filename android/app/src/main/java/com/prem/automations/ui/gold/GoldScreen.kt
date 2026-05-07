package com.prem.automations.ui.gold

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart
import com.patrykandpatrick.vico.core.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.core.cartesian.data.lineSeries
import com.prem.automations.data.api.dto.GoldPrediction
import com.prem.automations.ui.components.JobProgressDialog
import com.prem.automations.ui.components.RunFlagsDialog
import com.prem.automations.ui.components.StateContainer
import com.prem.automations.ui.theme.PnlAmber
import com.prem.automations.ui.theme.PnlGreen
import com.prem.automations.ui.theme.PnlRed
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GoldScreen(vm: GoldViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    val job by vm.job.collectAsState()
    val error by vm.error.collectAsState()
    var showRun by remember { mutableStateOf(false) }
    val snackHost = remember { SnackbarHostState() }
    LaunchedEffect(error) { error?.let { snackHost.showSnackbar(it); vm.clearError() } }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Gold") },
                actions = { TextButton(onClick = vm::refresh) { Text("Refresh") } },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showRun = true },
                icon = { Icon(Icons.Filled.PlayArrow, contentDescription = null) },
                text = { Text("Run now") },
            )
        },
        snackbarHost = { SnackbarHost(snackHost) },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            StateContainer(state, onRetry = vm::refresh) { gd ->
                Column(
                    Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    HeroCard(gd.latest.latest)
                    StatsCard(
                        accuracy = gd.latest.accuracy,
                        bias = gd.latest.biasCorrection,
                        total = gd.latest.totalPredictions,
                    )
                    HistoryChart(gd.history.predictions)
                }
            }
        }
    }
    if (showRun) {
        RunFlagsDialog(
            title = "Run gold notifier",
            flagOptions = listOf("--now", "--dry-run", "--morning", "--afternoon", "--check"),
            initialSelected = setOf("--now"),
            onDismiss = { showRun = false },
            onConfirm = { flags -> vm.runNow(flags) },
        )
    }
    JobProgressDialog(job = job, onDismiss = vm::dismissJob)
}

@Composable
private fun HeroCard(latest: GoldPrediction?) {
    val recoColor = when (latest?.recommendation?.uppercase()) {
        "BUY" -> PnlGreen
        "SELL" -> PnlRed
        else -> PnlAmber
    }
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text("Today", style = MaterialTheme.typography.labelMedium)
            Spacer(Modifier.height(4.dp))
            Text(
                latest?.price?.let { "₹%,.0f / g".format(it) } ?: "—",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AssistChip(onClick = {}, label = {
                    Text(latest?.recommendation ?: "—", color = recoColor)
                })
                latest?.predictedDirection?.let {
                    AssistChip(onClick = {}, label = { Text("Pred: $it") })
                }
                latest?.confidence?.let {
                    AssistChip(onClick = {}, label = { Text("conf %.0f%%".format(it * 100)) })
                }
            }
            latest?.date?.let {
                Spacer(Modifier.height(4.dp))
                Text(it, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun StatsCard(accuracy: Double?, bias: Double?, total: Int?) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            StatCol("Accuracy", accuracy?.let { "%.1f%%".format(it * 100) } ?: "—")
            StatCol("Bias", bias?.let { "%+.3f".format(it) } ?: "—")
            StatCol("Predictions", total?.toString() ?: "—")
        }
    }
}

@Composable
private fun StatCol(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun HistoryChart(predictions: List<GoldPrediction>) {
    val prices = predictions.mapNotNull { it.price ?: it.actualPrice }
    if (prices.size < 2) {
        Text("Not enough data for chart yet.", style = MaterialTheme.typography.bodySmall)
        return
    }
    val producer = remember { CartesianChartModelProducer() }
    val scope = rememberCoroutineScope()
    LaunchedEffect(prices) {
        scope.launch {
            producer.runTransaction {
                lineSeries { series(prices) }
            }
        }
    }
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("Last ${prices.size} days", style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(8.dp))
            CartesianChartHost(
                chart = rememberCartesianChart(rememberLineCartesianLayer()),
                modelProducer = producer,
                modifier = Modifier.fillMaxWidth().height(200.dp),
            )
        }
    }
}
