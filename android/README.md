# Automations Android app

Native Kotlin + Jetpack Compose dashboard that aggregates results from the
stock analyzer, gold notifier, paper trader, and live trader through the
FastAPI backend in `../server`.

## Stack

- Kotlin 2.0.20, AGP 8.5.2, min SDK 26, target SDK 35
- Jetpack Compose (BOM 2024.09), Material 3
- Hilt for DI, Retrofit + Moshi (KSP) for HTTP
- Vico for charts, Coil for images, DataStore for settings

## First-time setup

1. Open the `android/` folder in Android Studio (Hedgehog or newer).
2. Let Studio create the Gradle wrapper if it isn't present
   (`Tools → Gradle → Generate Wrapper`, or run `gradle wrapper` once).
3. Sync the project. KSP will generate Hilt + Moshi adapters on the first build.
4. Build the debug APK: `./gradlew :app:assembleDebug`
   (output: `app/build/outputs/apk/debug/app-debug.apk`).

## Configuring the API

On first launch, open the **Settings** tab and enter:

- **Base URL** — e.g. `https://yourname.pythonanywhere.com`
- **Bearer token** — value of the server-side `APP_API_TOKEN`

Both are stored locally via DataStore. Changes take effect immediately
(an OkHttp interceptor rewrites the request URL/host and adds the
`Authorization` header at request time, so no app restart is needed).

## Tabs

| Tab | Backend endpoints | Notes |
| --- | ----------------- | ----- |
| Stocks | `GET /stock/latest`, `GET /stock/reports/{name}` | Sub-tabs for Intraday/Swing/Holding/Sell. Tap a card → detail screen with technicals, prediction, levels, fundamentals, sentiment. |
| Gold | `GET /gold/latest`, `GET /gold/history?days=30` | Hero card with BUY/HOLD/SELL chip, accuracy stats, 30-day price chart (Vico). |
| Paper | `GET /paper/state`, `GET /paper/reports` | KPIs (today / cumulative / win-rate), Open/Closed sub-tabs, latest text-report viewer. |
| Live | `GET /live/state` | Same KPIs as Paper, read-only banner. |
| Settings | — | Base URL + token + version. |

## Phase 3 — Triggers, manual close, push notifications

All Phase 3 features are now wired:

- **Run-now FABs** on Stocks / Gold / Paper tabs trigger the matching
  `POST /…/run` endpoint and poll `GET /jobs/{id}` until the subprocess
  finishes (1 → 2 → 5 s back-off).
- **Manual close** — open the Paper tab → Open positions → tap **Close**.
  A dialog asks for the exit price (defaults to entry), shows an estimated
  P&L using the same `0.0015` round-trip cost as the backend, and calls
  `POST /paper/positions/{symbol}/close`.
- **Firebase Cloud Messaging** — see below.

### Firebase Cloud Messaging setup

The backend already publishes to topics `stock_reports`, `gold_updates`,
`paper_reports`, and `live_alerts` (see `lib/fcm.py`). The app subscribes
to whichever are toggled on in **Settings**.

To enable on the device:

1. In the Firebase console, register an Android app with package name
   `com.prem.automations` and download `google-services.json`.
2. Drop the file into `android/app/google-services.json`. The Gradle
   `google-services` plugin is wired but only applied when this file
   exists, so the project still builds without it (no notifications).
3. In the same Firebase project, generate a service-account key
   (`Project settings → Service accounts → Generate new private key`),
   save it on the server, and point the backend at it via
   `FCM_CREDENTIALS_JSON=/abs/path/key.json` (or
   `FCM_CREDENTIALS_INLINE='{…}'`). Set `FCM_PROJECT_ID` to your project
   ID.
4. On Android 13+, when you flip a Settings toggle on for the first time,
   the app will request the `POST_NOTIFICATIONS` runtime permission.

## Notes / known limitations

- No app icon yet (uses the system default).
- No persistent in-memory cache between tab switches; each tab refetches on
  first compose. WorkManager periodic refresh is set up in dependencies but
  not yet scheduled.
- Cleartext HTTP is disabled. If you point at a `http://` URL during dev,
  also add a network-security-config exception.
