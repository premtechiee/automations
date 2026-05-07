package com.prem.automations.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Generic checkbox-list dialog for picking script flags. */
@Composable
fun RunFlagsDialog(
    title: String,
    flagOptions: List<String>,
    initialSelected: Set<String> = setOf(flagOptions.firstOrNull().orEmpty()),
    extraContent: @Composable ColumnScope.() -> Unit = {},
    onDismiss: () -> Unit,
    onConfirm: (List<String>) -> Unit,
) {
    var selected by remember { mutableStateOf(initialSelected.filter { it.isNotBlank() }.toSet()) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                flagOptions.forEach { flag ->
                    Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                        Checkbox(
                            checked = flag in selected,
                            onCheckedChange = { on ->
                                selected = if (on) selected + flag else selected - flag
                            },
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(flag, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                extraContent()
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(selected.toList()); onDismiss() }) { Text("Run") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}
