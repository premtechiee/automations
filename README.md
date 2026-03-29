# Automations

A structured collection of personal automations built with Python.

## Repository layout

```
automations/
├── lib/                        # Common library (proxy, logging, WhatsApp)
│   ├── proxy.py                # Intel VPN auto-detection & proxy config
│   ├── logging_setup.py        # get_logger() factory
│   └── whatsapp.py             # Green API WhatsApp helpers
├── src/
│   └── gold_notifier/          # Gold & silver price notifier
│       ├── config.py           # All constants / env-var overrides
│       ├── fetchers.py         # Price fetching (yfinance, IBJA, goodreturns)
│       ├── analysis.py         # Technical & geo-political analysis
│       ├── prediction.py       # Self-learning price prediction model
│       ├── formatter.py        # WhatsApp message formatter
│       ├── image.py            # Pillow price-card image generator
│       ├── scheduler.py        # Scheduled jobs (morning / afternoon / alert)
│       └── main.py             # Orchestration entry point
├── scripts/
│   └── gold_notifier.py        # CLI runner
├── data/                       # Runtime outputs (logs, model, images) — gitignored
├── .env.example                # Document required environment variables
└── requirements.txt
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
copy .env.example .env
#    Edit .env with your Green API instance/token and recipient phone number.

# 3. (Optional) Set environment variables instead of editing config.py
set GOLD_PHONE_NUMBER=91XXXXXXXXXX@c.us
set GREEN_API_INSTANCE=71XXXXXXXX
set GREEN_API_TOKEN=your_token
```

## Running the gold notifier

```bash
# Start automated scheduler (morning 09:00 + afternoon 14:30 + 30-min threshold checks)
python scripts/gold_notifier.py

# One-shot update – fetch, format, and send immediately
python scripts/gold_notifier.py --now

# Dry run – fetch and print preview, do NOT send WhatsApp message
python scripts/gold_notifier.py --dry-run

# Send morning briefing manually
python scripts/gold_notifier.py --morning

# Send afternoon check manually
python scripts/gold_notifier.py --afternoon

# Check price-alert thresholds
python scripts/gold_notifier.py --check

# Verify WhatsApp connection
python scripts/gold_notifier.py --test
```

## Intel VPN / proxy

The automation auto-detects whether it is running inside Intel's network by
probing `proxy-dmz.intel.com:912` at startup (2-second timeout).  
If reachable, `HTTPS_PROXY` is set to `http://proxy-dmz.intel.com:912` — no
manual configuration needed.

## Adding a new automation

1. Create `automations/<your_automation>/` package with its own `config.py` and `main.py`.
2. Import shared utilities from `lib.proxy`, `lib.logging_setup`, `lib.whatsapp`.
3. Add a runner script under `scripts/`.

