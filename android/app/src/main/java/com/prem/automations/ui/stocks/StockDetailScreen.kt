package com.prem.automations.ui.stocks

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.prem.automations.data.api.dto.StockPick
import com.prem.automations.ui.components.StateContainer

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StockDetailScreen(
    symbol: String,
    onBack: () -> Unit,
    vm: StocksViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(symbol) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        }
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            StateContainer(state, onRetry = vm::refresh) { report ->
                val pick = report.buckets?.values?.flatten()?.firstOrNull { it.symbol == symbol }
                if (pick == null) {
                    Box(Modifier.fillMaxSize(), Alignment.Center) {
                        Text("Pick not found in latest report.")
                    }
                } else {
                    PickDetail(pick)
                }
            }
        }
    }
}

@Composable
private fun PickDetail(p: StockPick) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Section("Overview") {
            KV("Name", p.name ?: "—")
            KV("Sector", p.sector ?: "—")
            KV("Price", p.price?.let { "₹%.2f".format(it) } ?: "—")
            KV("Composite", p.composite?.let { "%.2f".format(it) } ?: "—")
            KV("Bucket score", p.bucketScore?.let { "%.2f".format(it) } ?: "—")
        }
        p.predict?.let { pr ->
            Section("Prediction") {
                KV("Direction", pr.direction ?: "—")
                KV("Confidence", pr.confidence?.let { "%.0f%%".format(it * 100) } ?: "—")
                KV("Score", pr.score?.let { "%.2f".format(it) } ?: "—")
                if (!pr.reasons.isNullOrEmpty()) {
                    Text("Reasons", fontWeight = FontWeight.SemiBold)
                    pr.reasons.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        p.tech?.let { t ->
            Section("Technicals") {
                KV("RSI(14)", t.rsi14?.let { "%.1f".format(it) } ?: "—")
                KV("MACD", t.macd?.let { "%.2f".format(it) } ?: "—")
                KV("MACD signal", t.macdSig?.let { "%.2f".format(it) } ?: "—")
                KV("ATR(14)", t.atr14?.let { "%.2f".format(it) } ?: "—")
                KV("ATR %", t.atrPct?.let { "%.2f%%".format(it) } ?: "—")
                KV("Volume ratio", t.volRatio?.let { "%.2f".format(it) } ?: "—")
                KV("EMA20", t.ema20?.let { "%.2f".format(it) } ?: "—")
                KV("EMA50", t.ema50?.let { "%.2f".format(it) } ?: "—")
                KV("EMA200", t.ema200?.let { "%.2f".format(it) } ?: "—")
                KV("Trend up", t.trendUp?.toString() ?: "—")
                KV("Δ 1d / 5d / 1m / 3m", "%s / %s / %s / %s".format(
                    t.chg1d?.let { "%.2f%%".format(it) } ?: "—",
                    t.chg5d?.let { "%.2f%%".format(it) } ?: "—",
                    t.chg1m?.let { "%.2f%%".format(it) } ?: "—",
                    t.chg3m?.let { "%.2f%%".format(it) } ?: "—",
                ))
            }
        }
        p.levels?.let { lv ->
            Section("Levels") {
                KV("Entry", lv.entry?.let { "₹%.2f".format(it) } ?: "—")
                KV("Target", lv.target?.let { "₹%.2f".format(it) } ?: "—")
                KV("Stop-loss", lv.sl?.let { "₹%.2f".format(it) } ?: "—")
                KV("Support", lv.support?.let { "₹%.2f".format(it) } ?: "—")
                KV("Resistance", lv.resistance?.let { "₹%.2f".format(it) } ?: "—")
                KV("Expected profit", lv.expectedProfitPct?.let { "%.2f%%".format(it) } ?: "—")
                KV("Risk", lv.riskPct?.let { "%.2f%%".format(it) } ?: "—")
                KV("R:R", lv.rr?.let { "%.2f".format(it) } ?: "—")
                KV("Hold (days)", lv.estHoldDays?.let { "%.1f".format(it) } ?: "—")
                KV("Hint", lv.holdHint ?: "—")
                KV("Buy window", lv.buyWindow ?: "—")
            }
        }
        p.fund?.let {
            Section("Fundamentals") {
                listOf("pe", "pb", "roe", "de", "mcap", "score").forEach { k ->
                    KV(k.uppercase(), it[k]?.toString() ?: "—")
                }
            }
        }
        p.senti?.let {
            Section("Sentiment") {
                KV("Score", it["score"]?.toString() ?: "—")
                KV("Positive", it["pos"]?.toString() ?: "—")
                KV("Negative", it["neg"]?.toString() ?: "—")
            }
        }
        if (!p.patterns.isNullOrEmpty()) {
            Section("Patterns") {
                p.patterns.forEach { Text("• $it") }
            }
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    ElevatedCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            HorizontalDivider()
            content()
        }
    }
}

@Composable
private fun KV(k: String, v: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(k, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(v, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
    }
}
