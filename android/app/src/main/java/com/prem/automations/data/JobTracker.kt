package com.prem.automations.data

import com.prem.automations.data.api.ApiService
import com.prem.automations.data.api.dto.JobInfo
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Polls a job until it terminates or the caller cancels the flow.
 *
 * Emits the latest [JobInfo] each tick, including the terminal state. The
 * polling cadence backs off slightly so a job that finishes quickly is seen
 * fast while long jobs don't hammer the server.
 */
@Singleton
class JobTracker @Inject constructor(private val api: ApiService) {

    fun track(id: String): Flow<JobInfo> = flow {
        var attempt = 0
        while (true) {
            val info = api.job(id)
            emit(info)
            if (info.status == "done" || info.status == "failed") return@flow
            attempt += 1
            // 1s for first 5 polls, then 2s, then 4s (capped at 5s).
            val waitMs = when {
                attempt < 5  -> 1_000L
                attempt < 15 -> 2_000L
                else         -> 5_000L
            }
            delay(waitMs)
        }
    }
}
