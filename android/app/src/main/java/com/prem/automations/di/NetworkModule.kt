package com.prem.automations.di

import android.content.Context
import com.prem.automations.data.Settings
import com.prem.automations.data.SettingsStore
import com.prem.automations.data.api.ApiService
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.launchIn
import okhttp3.Cache
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun moshi(): Moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    @Provides
    @Singleton
    fun client(
        @ApplicationContext appContext: Context,
        settings: SettingsStore,
    ): OkHttpClient {
        // Non-blocking cached snapshot of settings, refreshed on every change.
        // This avoids `runBlocking` on every HTTP call.
        val snapshot = AtomicReference(Settings("", ""))
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        settings.flow
            .onEach { snapshot.set(it) }
            .launchIn(scope)

        val log = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val cacheDir = File(appContext.cacheDir, "http-cache")
        val cache = Cache(cacheDir, 10L * 1024 * 1024) // 10 MB

        return OkHttpClient.Builder()
            .cache(cache)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            // Rewrite scheme/host/port at request time so settings changes
            // (base URL + token) take effect without an app restart.
            .addInterceptor { chain ->
                val current = snapshot.get()
                var req = chain.request()
                val configured = current.baseUrl.takeIf { it.isNotBlank() }
                    ?.let { (if (it.endsWith("/")) it else "$it/").toHttpUrlOrNull() }
                if (configured != null) {
                    val newUrl = req.url.newBuilder()
                        .scheme(configured.scheme)
                        .host(configured.host)
                        .port(configured.port)
                        .build()
                    req = req.newBuilder().url(newUrl).build()
                }
                if (current.token.isNotBlank()) {
                    req = req.newBuilder()
                        .addHeader("Authorization", "Bearer ${current.token}")
                        .build()
                }
                chain.proceed(req)
            }
            .addNetworkInterceptor { chain ->
                // Honour caching for safe GETs (server may not set headers).
                val resp = chain.proceed(chain.request())
                if (chain.request().method == "GET") {
                    resp.newBuilder()
                        .header("Cache-Control", "public, max-age=15")
                        .removeHeader("Pragma")
                        .build()
                } else resp
            }
            .addInterceptor(log)
            .build()
    }

    @Provides
    @Singleton
    fun retrofit(client: OkHttpClient, moshi: Moshi): Retrofit =
        Retrofit.Builder()
            // Placeholder; the interceptor above rewrites scheme/host/port.
            .baseUrl("http://placeholder.invalid/")
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()

    @Provides
    @Singleton
    fun api(retrofit: Retrofit): ApiService = retrofit.create(ApiService::class.java)
}
