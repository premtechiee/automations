# Automations API

A small FastAPI server that exposes the read-only `data/` artifacts produced by
the automations (stock analyzer, gold notifier, paper/live trader) as JSON
endpoints, lets clients trigger runs, and pushes Firebase Cloud Messaging
notifications for the companion Android app.

## Endpoints

All routes (except `GET /healthz`) require `Authorization: Bearer <APP_API_TOKEN>`.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/healthz` | Liveness probe (public) |
| GET  | `/stock/reports` | List stock-analyzer report filenames (newest-first) |
| GET  | `/stock/latest` | Latest stock-analyzer report JSON |
| GET  | `/stock/reports/{name}` | Specific stock report |
| GET  | `/gold/latest` | Latest gold prediction + accuracy/weights |
| GET  | `/gold/history?days=30` | Trimmed prediction history for charting |
| GET  | `/paper/state` | `data/paper_trader_state.json` |
| GET  | `/paper/reports` | List paper-report text files |
| GET  | `/paper/reports/{name}` | One paper report (UTF-8 text) |
| POST | `/paper/positions/{symbol}/close` | Manually close an open paper position |
| GET  | `/live/state` | `data/auto_trader_state.json` |
| GET  | `/assets/stock/{date}/{name}` | PNG/PDF artifact under `logs/stock_analyzer/` |
| GET  | `/assets/gold/{date}/{name}` | PNG artifact under `logs/gold_notifier/` |
| POST | `/stock/run` | Trigger `scripts/stock_analyzer.py` (rate-limited 1/min) |
| POST | `/gold/run`  | Trigger `scripts/gold_notifier.py` (1/min) |
| POST | `/paper/run` | Trigger paper-trade tick or `paper-trade-and-report` (1/5min) |
| GET  | `/jobs` / `/jobs/{id}` | List or poll trigger jobs |

## Environment

| Var | Required | Notes |
| --- | -------- | ----- |
| `APP_API_TOKEN` | yes | Bearer token clients must present. The server refuses to start if unset. |
| `FCM_PROJECT_ID` | optional | GCP project id for FCM HTTP v1 sends. |
| `FCM_CREDENTIALS_JSON` | optional | Path to service-account JSON. |
| `FCM_CREDENTIALS_INLINE` | optional | Service-account JSON content inline (single-line). |

If neither `FCM_*` is set, push notifications silently no-op so the rest of the
API still works.

## Run locally

```powershell
pip install -r requirements.txt -r server/requirements.txt
$env:APP_API_TOKEN = "dev-token"
uvicorn server.app:app --reload --port 8000
```

Smoke test:

```powershell
curl -H "Authorization: Bearer dev-token" http://127.0.0.1:8000/stock/latest
```

## Deploy on PythonAnywhere

1. Upload (or `git pull`) the repo into your PA home (e.g. `~/automations`).
2. Create a virtualenv and install both requirement files.
3. **Web tab → Add new web app → Manual configuration (Python 3.11+)**.
4. Set the WSGI file to call uvicorn via ASGI middleware. Recommended: use
   PythonAnywhere's "ASGI" beta if available; otherwise wrap with
   [`asgiref.wsgi.WsgiToAsgi`] (note: PA's stable web tier is WSGI-only, so
   you may want to deploy via `uvicorn` running under an "Always-on task"
   bound to a port, then proxy through PA's HTTP).
5. Set env vars in the web tab's *Environment variables* section
   (`APP_API_TOKEN`, optional `FCM_*`).
6. Make sure the same checkout is used by your scheduled tasks (so writes to
   `data/` are visible to the API process).

## Triggering safety

`POST /*/run` endpoints validate flags against an allow-list (only flags
already documented for each script are accepted) and are rate-limited
in-process. Trigger jobs run as `python -u scripts/<x>.py …` from the repo
root; stdout/stderr tails are exposed via `GET /jobs/{id}`.

## Manual paper-trade close

`POST /paper/positions/{SYMBOL}/close` body:

```json
{ "exit_price": 1234.5 }
```

Behaviour mirrors `src/angel_one/auto_trader.py`:

- Removes the trade from `open_trades`, appends to `closed_today` with
  `status = "CLOSED_MANUAL"`.
- Computes P&L using the same round-trip cost model
  (`cost = avg_notional × 0.0015`).
- Updates `realised_pnl`, `cumulative_pnl`, `cumulative_wins/losses`.
- Persists back to `data/paper_trader_state.json`.
