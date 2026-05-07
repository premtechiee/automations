package com.prem.automations.ui.paper

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.prem.automations.data.JobTracker
import com.prem.automations.data.PaperRepository
import com.prem.automations.data.api.dto.JobInfo
import com.prem.automations.data.api.dto.PaperReportsList
import com.prem.automations.data.api.dto.PaperRunBody
import com.prem.automations.data.api.dto.TraderState
import com.prem.automations.ui.UiState
import com.prem.automations.ui.safeCall
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

@HiltViewModel
class PaperViewModel @Inject constructor(
    private val repo: PaperRepository,
    private val jobs: JobTracker,
) : ViewModel() {
    private val _state = MutableStateFlow<UiState<TraderState>>(UiState.Idle)
    val state: StateFlow<UiState<TraderState>> = _state.asStateFlow()

    private val _reports = MutableStateFlow<PaperReportsList?>(null)
    val reports: StateFlow<PaperReportsList?> = _reports.asStateFlow()

    private val _job = MutableStateFlow<JobInfo?>(null)
    val job: StateFlow<JobInfo?> = _job.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = UiState.Loading
        viewModelScope.launch {
            _state.value = safeCall { repo.state() }
            runCatching { repo.reports() }.getOrNull()?.let { _reports.value = it }
        }
    }

    fun runNow(atEod: Boolean, send: Boolean, refreshPicks: Boolean) {
        viewModelScope.launch {
            try {
                val started = repo.run(
                    PaperRunBody(atEod = atEod, send = send, refreshPicks = refreshPicks)
                )
                _job.value = started
                jobs.track(started.id).collect { info ->
                    _job.value = info
                    if (info.status == "done") refresh()
                }
            } catch (t: Throwable) {
                _error.value = t.message ?: "Failed to start run"
            }
        }
    }

    fun closePosition(symbol: String, exitPrice: Double) {
        viewModelScope.launch {
            try {
                val updated = repo.close(symbol, exitPrice)
                _state.value = UiState.Success(updated)
            } catch (t: Throwable) {
                _error.value = t.message ?: "Close failed"
            }
        }
    }

    fun dismissJob() { _job.value = null }
    fun clearError() { _error.value = null }
}
