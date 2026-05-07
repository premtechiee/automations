package com.prem.automations.data

import com.prem.automations.data.api.ApiService
import com.prem.automations.data.api.dto.*
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class StockRepository @Inject constructor(private val api: ApiService) {
    suspend fun latest(): StockReportEnvelope = api.stockLatest()
    suspend fun reports(): List<String> = api.stockReports().reports
    suspend fun report(name: String): StockReportEnvelope = api.stockReport(name)
    suspend fun run(body: StockRunBody = StockRunBody()): JobInfo = api.stockRun(body).job
}

@Singleton
class GoldRepository @Inject constructor(private val api: ApiService) {
    suspend fun latest(): GoldLatest = api.goldLatest()
    suspend fun history(days: Int = 30): GoldHistory = api.goldHistory(days)
    suspend fun run(body: GoldRunBody = GoldRunBody()): JobInfo = api.goldRun(body).job
}

@Singleton
class PaperRepository @Inject constructor(private val api: ApiService) {
    suspend fun state(): TraderState = api.paperState()
    suspend fun reports(): PaperReportsList = api.paperReports()
    suspend fun report(name: String): PaperReportText = api.paperReport(name)
    suspend fun close(symbol: String, exitPrice: Double): TraderState =
        api.paperClose(symbol, ClosePositionBody(exitPrice)).state
    suspend fun run(body: PaperRunBody = PaperRunBody()): JobInfo = api.paperRun(body).job
}

@Singleton
class LiveRepository @Inject constructor(private val api: ApiService) {
    suspend fun state(): TraderState = api.liveState()
}

@Singleton
class JobsRepository @Inject constructor(private val api: ApiService) {
    suspend fun get(id: String): JobInfo = api.job(id)
}
