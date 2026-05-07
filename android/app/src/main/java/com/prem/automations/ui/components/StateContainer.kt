package com.prem.automations.ui.components

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.tween
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.prem.automations.ui.UiState

@Composable
fun <T> StateContainer(
    state: UiState<T>,
    onRetry: (() -> Unit)? = null,
    skeleton: @Composable () -> Unit = { DefaultSkeleton() },
    content: @Composable (T) -> Unit,
) {
    AnimatedContent(
        targetState = state,
        transitionSpec = {
            (fadeIn(tween(220)) togetherWith fadeOut(tween(120)))
        },
        label = "state-anim",
    ) { s ->
        when (s) {
            UiState.Idle -> Box(Modifier.fillMaxSize()) { skeleton() }
            UiState.Loading -> Box(Modifier.fillMaxSize()) { skeleton() }
            is UiState.Error -> ErrorView(message = s.message, onRetry = onRetry)
            is UiState.Success -> content(s.data)
        }
    }
}

@Composable
private fun ErrorView(message: String, onRetry: (() -> Unit)?) {
    Box(
        Modifier
            .fillMaxSize()
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                Icons.Filled.ErrorOutline,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.error,
            )
            Spacer(Modifier.height(8.dp))
            Text("Something went wrong", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            Text(
                message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (onRetry != null) {
                Spacer(Modifier.height(12.dp))
                FilledTonalButton(onClick = onRetry) { Text("Retry") }
            }
        }
    }
}

@Composable
fun DefaultSkeleton(padding: PaddingValues = PaddingValues(16.dp)) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(padding),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        ShimmerLine(height = 28.dp, fraction = 0.6f)
        ShimmerLine(height = 88.dp)
        ShimmerLine(height = 14.dp, fraction = 0.4f)
        repeat(4) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(72.dp)
                    .padding(top = 4.dp),
            ) { ShimmerLine(height = 72.dp) }
        }
    }
}
