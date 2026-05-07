package com.prem.automations.ui.components

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.prem.automations.data.api.dto.JobInfo
import com.prem.automations.ui.theme.PnlGreen
import com.prem.automations.ui.theme.PnlRed

/** Modal that shows live progress for a triggered automation job. */
@Composable
fun JobProgressDialog(
    job: JobInfo?,
    onDismiss: () -> Unit,
) {
    if (job == null) return
    val terminal = job.status == "done" || job.status == "failed"
    val title = when (job.kind) {
        "stock" -> "Stock analyzer"
        "gold"  -> "Gold notifier"
        "paper" -> "Paper trader"
        else    -> job.kind
    }
    val statusColor = when (job.status) {
        "done"   -> PnlGreen
        "failed" -> PnlRed
        else     -> MaterialTheme.colorScheme.primary
    }
    AlertDialog(
        onDismissRequest = { if (terminal) onDismiss() },
        title = { Text(title) },
        text = {
            Column(
                Modifier.fillMaxWidth().heightIn(max = 360.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                    if (!terminal) {
                        CircularProgressIndicator(
                            strokeWidth = 2.dp,
                            modifier = Modifier.size(16.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    Text(job.status.uppercase(), color = statusColor)
                }
                val tail = (job.stdoutTail + job.stderrTail).takeLast(40)
                if (tail.isNotEmpty()) {
                    Text(
                        tail.joinToString("\n"),
                        fontFamily = FontFamily.Monospace,
                        fontSize = 11.sp,
                    )
                } else if (terminal) {
                    Text("(no output)", style = MaterialTheme.typography.bodySmall)
                }
                job.returnCode?.let { Text("exit code: $it", style = MaterialTheme.typography.labelSmall) }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss, enabled = terminal) {
                Text(if (terminal) "Close" else "Running…")
            }
        },
    )
}
