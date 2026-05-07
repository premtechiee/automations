package com.prem.automations.ui.theme

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// Indigo / teal accent palette — calm, finance-leaning, high contrast.
private val DarkColors = darkColorScheme(
    primary             = Color(0xFF7DD3FC),
    onPrimary           = Color(0xFF002636),
    primaryContainer    = Color(0xFF0E4A6E),
    onPrimaryContainer  = Color(0xFFCDEAFF),
    secondary           = Color(0xFFA7F3D0),
    onSecondary         = Color(0xFF003824),
    secondaryContainer  = Color(0xFF065F46),
    onSecondaryContainer = Color(0xFFD1FAE5),
    tertiary            = Color(0xFFF5D0FE),
    onTertiary          = Color(0xFF3B0764),
    background          = Color(0xFF0B1220),
    onBackground        = Color(0xFFE5E7EB),
    surface             = Color(0xFF111827),
    onSurface           = Color(0xFFE5E7EB),
    surfaceVariant      = Color(0xFF1F2937),
    onSurfaceVariant    = Color(0xFFCBD5E1),
    surfaceTint         = Color(0xFF7DD3FC),
    outline             = Color(0xFF334155),
    outlineVariant      = Color(0xFF1E293B),
    error               = Color(0xFFF87171),
    onError             = Color(0xFF450A0A),
    errorContainer      = Color(0xFF7F1D1D),
    onErrorContainer    = Color(0xFFFECACA),
)

private val LightColors = lightColorScheme(
    primary             = Color(0xFF0369A1),
    onPrimary           = Color(0xFFFFFFFF),
    primaryContainer    = Color(0xFFCDEAFF),
    onPrimaryContainer  = Color(0xFF002636),
    secondary           = Color(0xFF047857),
    onSecondary         = Color(0xFFFFFFFF),
    secondaryContainer  = Color(0xFFD1FAE5),
    onSecondaryContainer = Color(0xFF003824),
    tertiary            = Color(0xFF7C3AED),
    onTertiary          = Color(0xFFFFFFFF),
    background          = Color(0xFFF8FAFC),
    onBackground        = Color(0xFF0F172A),
    surface             = Color(0xFFFFFFFF),
    onSurface           = Color(0xFF0F172A),
    surfaceVariant      = Color(0xFFE2E8F0),
    onSurfaceVariant    = Color(0xFF334155),
    surfaceTint         = Color(0xFF0369A1),
    outline             = Color(0xFF94A3B8),
    outlineVariant      = Color(0xFFCBD5E1),
    error               = Color(0xFFB91C1C),
    onError             = Color(0xFFFFFFFF),
    errorContainer      = Color(0xFFFEE2E2),
    onErrorContainer    = Color(0xFF450A0A),
)

val PnlGreen = Color(0xFF10B981)
val PnlRed = Color(0xFFEF4444)
val PnlAmber = Color(0xFFF59E0B)

@Composable
fun AutomationsTheme(
    useDark: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = true,
    content: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val supportsDynamic = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    val scheme = when {
        dynamicColor && supportsDynamic && useDark  -> dynamicDarkColorScheme(context)
        dynamicColor && supportsDynamic && !useDark -> dynamicLightColorScheme(context)
        useDark                                     -> DarkColors
        else                                        -> LightColors
    }

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window ?: return@SideEffect
            @Suppress("DEPRECATION")
            window.statusBarColor = android.graphics.Color.TRANSPARENT
            @Suppress("DEPRECATION")
            window.navigationBarColor = android.graphics.Color.TRANSPARENT
            val controller = WindowCompat.getInsetsController(window, view)
            controller.isAppearanceLightStatusBars = !useDark
            controller.isAppearanceLightNavigationBars = !useDark
        }
    }

    MaterialTheme(
        colorScheme = scheme,
        typography  = AppTypography,
        shapes      = AppShapes,
        content     = content,
    )
}
