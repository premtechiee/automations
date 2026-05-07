package com.prem.automations.ui

import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.AutoGraph
import androidx.compose.material.icons.filled.MonetizationOn
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.AutoGraph
import androidx.compose.material.icons.outlined.MonetizationOn
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.ShowChart
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.prem.automations.ui.gold.GoldScreen
import com.prem.automations.ui.live.LiveScreen
import com.prem.automations.ui.paper.PaperReportScreen
import com.prem.automations.ui.paper.PaperScreen
import com.prem.automations.ui.settings.SettingsScreen
import com.prem.automations.ui.stocks.StockDetailScreen
import com.prem.automations.ui.stocks.StocksScreen

private enum class TopDest(
    val route: String,
    val label: String,
    val icon: ImageVector,
    val iconSelected: ImageVector,
) {
    Stocks("stocks", "Stocks", Icons.Outlined.ShowChart, Icons.Filled.ShowChart),
    Gold("gold", "Gold", Icons.Outlined.MonetizationOn, Icons.Filled.MonetizationOn),
    Paper("paper", "Paper", Icons.Outlined.AutoGraph, Icons.Filled.AutoGraph),
    Live("live", "Live", Icons.Outlined.AccountBalance, Icons.Filled.AccountBalance),
    Settings("settings", "Settings", Icons.Outlined.Settings, Icons.Filled.Settings),
}

@Composable
fun RootScaffold() {
    val nav = rememberNavController()
    Scaffold(
        bottomBar = {
            NavigationBar(
                tonalElevation = 4.dp,
                containerColor = MaterialTheme.colorScheme.surface,
            ) {
                val backStack by nav.currentBackStackEntryAsState()
                val current = backStack?.destination
                TopDest.entries.forEach { dest ->
                    val selected = current?.hierarchy?.any { it.route == dest.route } == true
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            nav.navigate(dest.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = {
                            Icon(
                                if (selected) dest.iconSelected else dest.icon,
                                contentDescription = dest.label,
                            )
                        },
                        label = { Text(dest.label) },
                        colors = NavigationBarItemDefaults.colors(
                            indicatorColor = MaterialTheme.colorScheme.secondaryContainer,
                            selectedIconColor = MaterialTheme.colorScheme.onSecondaryContainer,
                            selectedTextColor = MaterialTheme.colorScheme.onSurface,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                    )
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = TopDest.Stocks.route,
            modifier = Modifier.padding(padding),
            enterTransition = {
                fadeIn(tween(220)) +
                    slideInHorizontally(tween(260)) { it / 16 }
            },
            exitTransition = { fadeOut(tween(160)) },
            popEnterTransition = {
                fadeIn(tween(220)) +
                    slideInHorizontally(tween(260)) { -it / 16 }
            },
            popExitTransition = { fadeOut(tween(160)) },
        ) {
            composable(TopDest.Stocks.route) {
                StocksScreen(onPickClick = { symbol -> nav.navigate("stockDetail/$symbol") })
            }
            composable("stockDetail/{symbol}") { entry ->
                StockDetailScreen(
                    symbol = entry.arguments?.getString("symbol").orEmpty(),
                    onBack = { nav.popBackStack() },
                )
            }
            composable(TopDest.Gold.route) { GoldScreen() }
            composable(TopDest.Paper.route) {
                PaperScreen(onOpenReport = { name -> nav.navigate("paperReport/$name") })
            }
            composable("paperReport/{name}") { entry ->
                PaperReportScreen(
                    name = entry.arguments?.getString("name").orEmpty(),
                    onBack = { nav.popBackStack() },
                )
            }
            composable(TopDest.Live.route) { LiveScreen() }
            composable(TopDest.Settings.route) { SettingsScreen() }
        }
    }
}
