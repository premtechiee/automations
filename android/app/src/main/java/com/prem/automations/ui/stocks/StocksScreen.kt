package com.prem.automations.ui.stocks

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.prem.automations.data.api.dto.StockPick
import com.prem.automations.ui.components.JobProgressDialog
import com.prem.automations.ui.components.RunFlagsDialog
import com.prem.automations.ui.components.StateContainer
import com.prem.automations.ui.theme.PnlAmber
import com.prem.automations.ui.theme.PnlGreen
import com.prem.automations.ui.theme.PnlRed

private val BUCKETS = listOf("intraday", "swing", "holding", "sell")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StocksScreen(
    onPickClick: (String) -> Unit,
    vm: StocksViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val name by vm.name.collectAsState()
    val job by vm.job.collectAsState()
    val error by vm.error.collectAsState()
    var bucketIdx by remember { mutableIntStateOf(0) }
    var showRun by remember { mutableStateOf(false) }
    val snackHost = remember { SnackbarHostState() }
    LaunchedEffect(error) { error?.let { snackHost.showSnackbar(it); vm.clearError() } }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Column {
                    Text("Stocks")
                    if (name != null) Text(
                        name!!,
                        style = MaterialTheme.typography.bodySmall,
                    )
                } },
                actions = {
                    TextButton(onClick = { vm.refresh() }) { Text("Refresh") }
                },
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
        Column(Modifier.padding(padding).fillMaxSize()) {
            TabRow(selectedTabIndex = bucketIdx) {
                BUCKETS.forEachIndexed { i, b ->
                    Tab(
                        selected = bucketIdx == i,
                        onClick = { bucketIdx = i },
                        text = { Text(b.replaceFirstChar(Char::uppercaseChar)) },
                    )
                }
            }
            StateContainer(state, onRetry = vm::refresh) { report ->
                val picks = report.buckets?.get(BUCKETS[bucketIdx]).orEmpty()
                if (picks.isEmpty()) {
                    Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text("No picks in this bucket.")
                    }
                } else {
                    LazyColumn(
                        contentPadding = PaddingValues(12.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(picks, key = { it.symbol }) { p ->
                            PickCard(p, onClick = { onPickClick(p.symbol) })
                        }
                    }
                }
            }
        }
    }
    if (showRun) {
        RunFlagsDialog(
            title = "Run stock analyzer",
            flagOptions = listOf("--now", "--dry-run", "--preopen", "--morning", "--afternoon", "--no-pdf"),
            initialSelected = setOf("--now"),
            onDismiss = { showRun = false },
            onConfirm = { flags -> vm.runNow(flags, channel = null) },
        )
    }
    JobProgressDialog(job = job, onDismiss = vm::dismissJob)
}

@Composable
private fun PickCard(p: StockPick, onClick: () -> Unit) {
    val direction = p.predict?.direction.orEmpty()
    val dirColor = when (direction.uppercase()) {
        "UP" -> PnlGreen
        "DOWN" -> PnlRed
        else -> PnlAmber
    }
    ElevatedCard(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(p.symbol, fontWeight = FontWeight.SemiBold)
                    if (!p.name.isNullOrBlank() && p.name != "—")
                        Text(p.name, style = MaterialTheme.typography.bodySmall)
                }
                Text(
                    p.price?.let { "₹%.2f".format(it) } ?: "—",
                    fontWeight = FontWeight.Medium,
                )
            }
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                AssistChip(
                    onClick = {},
                    label = { Text(direction.ifBlank { "—" }) },
                    colors = AssistChipDefaults.assistChipColors(labelColor = dirColor),
                )
                Spacer(Modifier.width(6.dp))
                p.predict?.confidence?.let {
                    AssistChip(onClick = {}, label = { Text("conf %.0f%%".format(it * 100)) })
                }
                Spacer(Modifier.width(6.dp))
                p.bucketScore?.let {
                    AssistChip(onClick = {}, label = { Text("score %.1f".format(it)) })
                }
            }
            val lv = p.levels
            if (lv != null) {
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    lv.entry?.let { Text("Entry ₹%.2f".format(it), style = MaterialTheme.typography.bodySmall) }
                    lv.target?.let { Text("Tgt ₹%.2f".format(it), color = PnlGreen, style = MaterialTheme.typography.bodySmall) }
                    lv.sl?.let { Text("SL ₹%.2f".format(it), color = PnlRed, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
    }
}
