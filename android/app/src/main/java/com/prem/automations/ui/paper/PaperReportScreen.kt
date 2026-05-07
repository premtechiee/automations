package com.prem.automations.ui.paper

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.prem.automations.data.PaperRepository
import com.prem.automations.data.api.dto.PaperReportText
import com.prem.automations.ui.UiState
import com.prem.automations.ui.components.StateContainer
import com.prem.automations.ui.safeCall
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

@HiltViewModel
class PaperReportViewModel @Inject constructor(
    private val repo: PaperRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<UiState<PaperReportText>>(UiState.Idle)
    val state: StateFlow<UiState<PaperReportText>> = _state.asStateFlow()

    fun load(name: String) {
        _state.value = UiState.Loading
        viewModelScope.launch {
            _state.value = safeCall { repo.report(name) }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PaperReportScreen(
    name: String,
    onBack: () -> Unit,
    vm: PaperReportViewModel = hiltViewModel(),
) {
    LaunchedEffect(name) { vm.load(name) }
    val state by vm.state.collectAsState()
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(name) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        }
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            StateContainer(state, onRetry = { vm.load(name) }) { rep ->
                Box(
                    Modifier.fillMaxSize()
                        .horizontalScroll(rememberScrollState())
                        .verticalScroll(rememberScrollState())
                        .padding(12.dp),
                ) {
                    Text(
                        rep.text,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                    )
                }
            }
        }
    }
}
