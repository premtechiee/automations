package com.prem.automations.ui.paper

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.text.KeyboardOptions
import androidx.hilt.navigation.compose.hiltViewModel
import com.prem.automations.data.api.dto.Trade
import com.prem.automations.data.api.dto.TraderState
import com.prem.automations.ui.components.JobProgressDialog
import com.prem.automations.ui.components.StateContainer
import com.prem.automations.ui.theme.PnlGreen
import com.prem.automations.ui.theme.PnlRed

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PaperScreen(
    onOpenReport: (String) -> Unit,
    vm: PaperViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val reports by vm.reports.collectAsState()
    val job by vm.job.collectAsState()
    val error by vm.error.collectAsState()
    var subTab by remember { mutableIntStateOf(0) }
    var showRun by remember { mutableStateOf(false) }
    var closeTarget by remember { mutableStateOf<Trade?>(null) }
    val snackHost = remember { SnackbarHostState() }
    LaunchedEffect(error) { error?.let { snackHost.showSnackbar(it); vm.clearError() } }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Paper trader") },
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
        Column(Modifier.padding(padding).fillMaxSize()) {
            StateContainer(state, onRetry = vm::refresh) { st ->
                Column(Modifier.fillMaxSize()) {
                    KpiHeader(st)
                    TabRow(selectedTabIndex = subTab) {
                        Tab(subTab == 0, { subTab = 0 }, text = { Text("Open (${st.openTrades.size})") })
                        Tab(subTab == 1, { subTab = 1 }, text = { Text("Closed (${st.closedToday.size})") })
                    }
                    val list = if (subTab == 0) st.openTrades else st.closedToday
                    Box(Modifier.weight(1f)) {
                        if (list.isEmpty()) {
                            Box(Modifier.fillMaxSize(), Alignment.Center) {
                                Text(if (subTab == 0) "No open positions." else "Nothing closed today.")
                            }
                        } else {
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(list, key = { it.symbol + (it.openedAt ?: "") }) { trade ->
                                    TradeCard(
                                        trade,
                                        canClose = subTab == 0,
                                        onClose = { closeTarget = trade },
                                    )
                                }
                            }
                        }
                    }
                    reports?.last?.let { last ->
                        HorizontalDivider()
                        TextButton(
                            onClick = { onOpenReport(last) },
                            modifier = Modifier.fillMaxWidth().padding(8.dp),
                        ) { Text("View latest report ($last)") }
                    }
                }
            }
        }
    }

    if (showRun) {
        var send by remember { mutableStateOf(false) }
        var refresh by remember { mutableStateOf(false) }
        var atEod by remember { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { showRun = false },
            title = { Text("Run paper trader") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    OptionRow("End-of-day square-off", atEod) { atEod = it }
                    OptionRow("Push report after run", send) { send = it }
                    OptionRow("Refresh picks first (paper-trade-and-report)", refresh) { refresh = it }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    vm.runNow(atEod = atEod, send = send, refreshPicks = refresh)
                    showRun = false
                }) { Text("Run") }
            },
            dismissButton = {
                TextButton(onClick = { showRun = false }) { Text("Cancel") }
            },
        )
    }

    closeTarget?.let { trade ->
        ClosePositionDialog(
            trade = trade,
            onDismiss = { closeTarget = null },
            onConfirm = { price ->
                vm.closePosition(trade.symbol, price)
                closeTarget = null
            },
        )
    }

    JobProgressDialog(job = job, onDismiss = vm::dismissJob)
}

@Composable
private fun OptionRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = checked, onCheckedChange = onChange)
        Spacer(Modifier.width(4.dp))
        Text(label, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ClosePositionDialog(
    trade: Trade,
    onDismiss: () -> Unit,
    onConfirm: (Double) -> Unit,
) {
    var raw by remember { mutableStateOf(trade.entryPrice.toString()) }
    val parsed = raw.toDoubleOrNull()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Close ${trade.symbol}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "Entry ₹%.2f · qty %d · SL ₹%.2f · Tgt ₹%.2f"
                        .format(trade.entryPrice, trade.qty, trade.sl, trade.target),
                    style = MaterialTheme.typography.bodySmall,
                )
                OutlinedTextField(
                    value = raw,
                    onValueChange = { raw = it },
                    label = { Text("Exit price") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
                if (parsed != null) {
                    val pnl = (parsed - trade.entryPrice) * trade.qty
                    val cost = ((parsed + trade.entryPrice) / 2.0) * trade.qty * 0.0015
                    val net = pnl - cost
                    Text(
                        "Estimated P&L: ₹%+,.0f  (gross ₹%+,.0f − cost ₹%.0f)".format(net, pnl, cost),
                        color = if (net >= 0) PnlGreen else PnlRed,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { parsed?.let(onConfirm) },
                enabled = parsed != null && parsed > 0,
            ) { Text("Close position") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun KpiHeader(st: TraderState) {
    val pnlColor = if (st.cumulativePnl >= 0) PnlGreen else PnlRed
    Row(
        Modifier.fillMaxWidth().padding(12.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        Kpi("Realised today", "₹%+,.0f".format(st.realisedPnl), if (st.realisedPnl >= 0) PnlGreen else PnlRed)
        Kpi("Cumulative", "₹%+,.0f".format(st.cumulativePnl), pnlColor)
        val total = st.cumulativeWins + st.cumulativeLosses
        val winRate = if (total > 0) st.cumulativeWins * 100.0 / total else 0.0
        Kpi("Win rate", "%.0f%%".format(winRate))
    }
    if (st.halted) {
        AssistChip(
            onClick = {},
            label = { Text("Halted: ${st.haltedReason ?: "—"}", color = PnlRed) },
            modifier = Modifier.padding(horizontal = 12.dp),
        )
    }
}

@Composable
private fun Kpi(label: String, value: String, color: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.onSurface) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, color = color, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun TradeCard(
    t: Trade,
    canClose: Boolean = false,
    onClose: () -> Unit = {},
) {
    val pnlColor = if (t.realisedPnl >= 0) PnlGreen else PnlRed
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column(Modifier.weight(1f)) {
                    Text(t.symbol, fontWeight = FontWeight.SemiBold)
                    Text("${t.bucket ?: "—"} · ${t.side ?: "BUY"} · qty ${t.qty}", style = MaterialTheme.typography.bodySmall)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(t.status, style = MaterialTheme.typography.labelSmall)
                    if (t.status != "OPEN") {
                        Text("₹%+,.0f".format(t.realisedPnl), color = pnlColor, fontWeight = FontWeight.Bold)
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Entry ₹%.2f".format(t.entryPrice), style = MaterialTheme.typography.bodySmall)
                Text("SL ₹%.2f".format(t.sl), style = MaterialTheme.typography.bodySmall, color = PnlRed)
                Text("Tgt ₹%.2f".format(t.target), style = MaterialTheme.typography.bodySmall, color = PnlGreen)
                t.exitPrice?.let { Text("Exit ₹%.2f".format(it), style = MaterialTheme.typography.bodySmall) }
            }
            t.openedAt?.let { Text("Opened $it", style = MaterialTheme.typography.labelSmall) }
            t.closedAt?.let { Text("Closed $it", style = MaterialTheme.typography.labelSmall) }
            if (canClose) {
                Spacer(Modifier.height(6.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    OutlinedButton(onClick = onClose) {
                        Icon(Icons.Filled.Close, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Close")
                    }
                }
            }
        }
    }
}
