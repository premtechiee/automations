package com.prem.automations.ui.gold

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.prem.automations.data.GoldRepository
import com.prem.automations.data.JobTracker
import com.prem.automations.data.api.dto.GoldHistory
import com.prem.automations.data.api.dto.GoldLatest
import com.prem.automations.data.api.dto.GoldRunBody
import com.prem.automations.data.api.dto.JobInfo
import com.prem.automations.ui.UiState
import com.prem.automations.ui.safeCall
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class GoldData(val latest: GoldLatest, val history: GoldHistory)

@HiltViewModel
class GoldViewModel @Inject constructor(
    private val repo: GoldRepository,
    private val jobs: JobTracker,
) : ViewModel() {
    private val _state = MutableStateFlow<UiState<GoldData>>(UiState.Idle)
    val state: StateFlow<UiState<GoldData>> = _state.asStateFlow()

    private val _job = MutableStateFlow<JobInfo?>(null)
    val job: StateFlow<JobInfo?> = _job.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = UiState.Loading
        viewModelScope.launch {
            _state.value = safeCall {
                coroutineScope {
                    val latest = async { repo.latest() }
                    val history = async { repo.history(30) }
                    GoldData(latest.await(), history.await())
                }
            }
        }
    }

    fun runNow(flags: List<String>) {
        viewModelScope.launch {
            try {
                val started = repo.run(GoldRunBody(flags = flags))
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
