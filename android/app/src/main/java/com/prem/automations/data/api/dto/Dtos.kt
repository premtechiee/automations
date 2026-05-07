package com.prem.automations.data.api.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

// ── Stock analyzer ────────────────────────────────────────────────────────────

@JsonClass(generateAdapter = true)
data class StockReportEnvelope(
    val name: String,
    val report: StockReport,
)

@JsonClass(generateAdapter = true)
data class StockReport(
    @Json(name = "generated_at") val generatedAt: String? = null,
    val buckets: Map<String, List<StockPick>>? = emptyMap(),
    val mfs: List<Map<String, Any>>? = null,
    val watchlist: List<Map<String, Any>>? = null,
    @Json(name = "market_forecast") val marketForecast: Map<String, Any>? = null,
)

@JsonClass(generateAdapter = true)
data class StockPick(
    val symbol: String,
    val name: String? = null,
    val sector: String? = null,
    val price: Double? = null,
    val tech: TechBlock? = null,
    val fund: Map<String, Any>? = null,
    val senti: Map<String, Any>? = null,
    val patterns: List<String>? = null,
    val sr: Map<String, Any>? = null,
    val predict: Predict? = null,
    val composite: Double? = null,
    @Json(name = "bucket_score") val bucketScore: Double? = null,
    val levels: Levels? = null,
)

@JsonClass(generateAdapter = true)
data class TechBlock(
    @Json(name = "chg_1d_pct") val chg1d: Double? = null,
    @Json(name = "chg_5d_pct") val chg5d: Double? = null,
    @Json(name = "chg_1m_pct") val chg1m: Double? = null,
    @Json(name = "chg_3m_pct") val chg3m: Double? = null,
    val rsi14: Double? = null,
    val macd: Double? = null,
    @Json(name = "macd_sig") val macdSig: Double? = null,
    @Json(name = "macd_hist") val macdHist: Double? = null,
    val ema20: Double? = null,
    val ema50: Double? = null,
    val ema200: Double? = null,
    val atr14: Double? = null,
    @Json(name = "atr_pct") val atrPct: Double? = null,
    @Json(name = "vol_ratio") val volRatio: Double? = null,
    @Json(name = "trend_up") val trendUp: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class Predict(
    val direction: String? = null,
    val confidence: Double? = null,
    val score: Double? = null,
    val reasons: List<String>? = null,
)

@JsonClass(generateAdapter = true)
data class Levels(
    val entry: Double? = null,
    val sl: Double? = null,
    val target: Double? = null,
    val support: Double? = null,
    val resistance: Double? = null,
    @Json(name = "expected_profit_pct") val expectedProfitPct: Double? = null,
    @Json(name = "risk_pct") val riskPct: Double? = null,
    val rr: Double? = null,
    @Json(name = "est_hold_days") val estHoldDays: Double? = null,
    @Json(name = "hold_hint") val holdHint: String? = null,
    @Json(name = "buy_window") val buyWindow: String? = null,
)

@JsonClass(generateAdapter = true)
data class StockReportsList(
    val reports: List<String>,
)

// ── Gold notifier ─────────────────────────────────────────────────────────────

@JsonClass(generateAdapter = true)
data class GoldLatest(
    val weights: Map<String, Double>? = null,
    val accuracy: Double? = null,
    @Json(name = "bias_correction") val biasCorrection: Double? = null,
    val latest: GoldPrediction? = null,
    @Json(name = "total_predictions") val totalPredictions: Int? = null,
)

@JsonClass(generateAdapter = true)
data class GoldHistory(
    val days: Int,
    val predictions: List<GoldPrediction>,
)

@JsonClass(generateAdapter = true)
data class GoldPrediction(
    val date: String? = null,
    val price: Double? = null,
    @Json(name = "predicted_direction") val predictedDirection: String? = null,
    @Json(name = "actual_direction") val actualDirection: String? = null,
    val correct: Boolean? = null,
    val confidence: Double? = null,
    val recommendation: String? = null,
    @Json(name = "predicted_price") val predictedPrice: Double? = null,
    @Json(name = "actual_price") val actualPrice: Double? = null,
)

// ── Paper / live trader ───────────────────────────────────────────────────────

@JsonClass(generateAdapter = true)
data class TraderState(
    val date: String? = null,
    @Json(name = "open_trades") val openTrades: List<Trade> = emptyList(),
    @Json(name = "closed_today") val closedToday: List<Trade> = emptyList(),
    @Json(name = "realised_pnl") val realisedPnl: Double = 0.0,
    @Json(name = "cumulative_pnl") val cumulativePnl: Double = 0.0,
    @Json(name = "cumulative_wins") val cumulativeWins: Int = 0,
    @Json(name = "cumulative_losses") val cumulativeLosses: Int = 0,
    val halted: Boolean = false,
    @Json(name = "halted_reason") val haltedReason: String? = null,
    val history: List<Map<String, Any>> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class Trade(
    val symbol: String,
    val bucket: String? = null,
    val side: String? = null,
    val qty: Int = 0,
    @Json(name = "entry_price") val entryPrice: Double = 0.0,
    val sl: Double = 0.0,
    val target: Double = 0.0,
    @Json(name = "order_id") val orderId: String? = null,
    @Json(name = "opened_at") val openedAt: String? = null,
    val status: String = "OPEN",
    @Json(name = "closed_at") val closedAt: String? = null,
    @Json(name = "exit_price") val exitPrice: Double? = null,
    @Json(name = "realised_pnl") val realisedPnl: Double = 0.0,
    @Json(name = "peak_price") val peakPrice: Double? = null,
    @Json(name = "initial_sl") val initialSl: Double? = null,
    @Json(name = "trail_active") val trailActive: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class PaperReportsList(
    val reports: List<String>,
    val last: String? = null,
)

@JsonClass(generateAdapter = true)
data class PaperReportText(
    val name: String,
    val text: String,
)

// ── Triggers ──────────────────────────────────────────────────────────────────

@JsonClass(generateAdapter = true)
data class JobInfo(
    val id: String,
    val kind: String,
    val cmd: List<String>,
    val status: String,
    @Json(name = "started_at") val startedAt: Double = 0.0,
    @Json(name = "finished_at") val finishedAt: Double = 0.0,
    @Json(name = "return_code") val returnCode: Int? = null,
    @Json(name = "stdout_tail") val stdoutTail: List<String> = emptyList(),
    @Json(name = "stderr_tail") val stderrTail: List<String> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class JobEnvelope(val job: JobInfo)

@JsonClass(generateAdapter = true)
data class StockRunBody(
    val flags: List<String> = listOf("--now"),
    val channel: String? = null,
    val theme: String? = null,
)

@JsonClass(generateAdapter = true)
data class GoldRunBody(val flags: List<String> = listOf("--now"))

@JsonClass(generateAdapter = true)
data class PaperRunBody(
    @Json(name = "at_eod") val atEod: Boolean = false,
    val send: Boolean = false,
    @Json(name = "refresh_picks") val refreshPicks: Boolean = false,
)

@JsonClass(generateAdapter = true)
data class ClosePositionBody(
    @Json(name = "exit_price") val exitPrice: Double,
)

@JsonClass(generateAdapter = true)
data class CloseResponse(
    val closed: String,
    val state: TraderState,
)
