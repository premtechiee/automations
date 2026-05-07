package com.prem.automations.data.api

import com.prem.automations.data.api.dto.*
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {
    @GET("stock/latest")        suspend fun stockLatest(): StockReportEnvelope
    @GET("stock/reports")       suspend fun stockReports(): StockReportsList
    @GET("stock/reports/{name}") suspend fun stockReport(@Path("name") name: String): StockReportEnvelope

    @GET("gold/latest")  suspend fun goldLatest(): GoldLatest
    @GET("gold/history") suspend fun goldHistory(@Query("days") days: Int = 30): GoldHistory

    @GET("paper/state")           suspend fun paperState(): TraderState
    @GET("paper/reports")         suspend fun paperReports(): PaperReportsList
    @GET("paper/reports/{name}")  suspend fun paperReport(@Path("name") name: String): PaperReportText

    @POST("paper/positions/{symbol}/close")
    suspend fun paperClose(
        @Path("symbol") symbol: String,
        @Body body: ClosePositionBody,
    ): CloseResponse

    @GET("live/state") suspend fun liveState(): TraderState

    @POST("stock/run") suspend fun stockRun(@Body body: StockRunBody): JobEnvelope
    @POST("gold/run")  suspend fun goldRun(@Body body: GoldRunBody): JobEnvelope
    @POST("paper/run") suspend fun paperRun(@Body body: PaperRunBody): JobEnvelope

    @GET("jobs/{id}") suspend fun job(@Path("id") id: String): JobInfo
}
