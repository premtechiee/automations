package com.prem.automations.ui

/** Generic UI state wrapper for screens that fetch data from the API. */
sealed interface UiState<out T> {
    data object Idle : UiState<Nothing>
    data object Loading : UiState<Nothing>
    data class Success<T>(val data: T) : UiState<T>
    data class Error(val message: String) : UiState<Nothing>
}

inline fun <T> safeCall(block: () -> T): UiState<T> = try {
    UiState.Success(block())
} catch (t: Throwable) {
    UiState.Error(t.message ?: t::class.java.simpleName)
}
