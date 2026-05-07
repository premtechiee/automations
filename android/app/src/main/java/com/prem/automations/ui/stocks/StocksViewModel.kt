package com.prem.automations.ui.stocks

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.prem.automations.data.JobTracker
import com.prem.automations.data.StockRepository
import com.prem.automations.data.api.dto.JobInfo
import com.prem.automations.data.api.dto.StockReport
import com.prem.automations.data.api.dto.StockRunBody
import com.prem.automations.ui.UiState
import com.prem.automations.ui.safeCall
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

@HiltViewModel
class StocksViewModel @Inject constructor(
    private val repo: StockRepository,
    private val jobs: JobTracker,
) : ViewModel() {

    private val _state = MutableStateFlow<UiState<StockReport>>(UiState.Idle)
    val state: StateFlow<UiState<StockReport>> = _state.asStateFlow()

    private val _name = MutableStateFlow<String?>(null)
    val name: StateFlow<String?> = _name.asStateFlow()

    private val _job = MutableStateFlow<JobInfo?>(null)
    val job: StateFlow<JobInfo?> = _job.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = UiState.Loading
        viewModelScope.launch {
            val r = safeCall { repo.latest() }
            when (r) {
                is UiState.Success -> {
                    _name.value = r.data.name
                    _state.value = UiState.Success(r.data.report)
                }
                is UiState.Error -> _state.value = r
                else -> {}
            }
        }
    }

    fun runNow(flags: List<String>, channel: String?) {
        viewModelScope.launch {
            try {
                val started = repo.run(StockRunBody(flags = flags, channel = channel))
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

    fun dismissJob() { _job.value = null }
    fun clearError() { _error.value = null }
}
