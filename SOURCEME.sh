#!/usr/bin/env bash
# sourceme.sh - dot-source this file to set up and activate the project venv
#
#   Usage (from the repo root):
#       source ./sourceme.sh
#
# What it does:
#   1. Creates .venv with python3 if it doesn't exist
#   2. Activates .venv in the current shell session
#   3. Upgrades pip silently
#   4. Installs / syncs requirements.txt

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
REQ="$SCRIPT_DIR/requirements.txt"

# 1. Create venv
if [ ! -f "$VENV/bin/python" ]; then
    echo "[sourceme] Creating virtual environment at .venv ..."
    python3 -m venv "$VENV"
else
    echo "[sourceme] .venv already exists - skipping creation."
fi

# 2. Activate
if [ ! -f "$VENV/bin/activate" ]; then
    echo "[sourceme] ERROR: activation script not found: $VENV/bin/activate"
    return 1
fi
echo "[sourceme] Activating .venv ..."
source "$VENV/bin/activate"

# 3. Upgrade pip
echo "[sourceme] Upgrading pip ..."
pip install --upgrade pip --quiet

# 4. Install dependencies
if [ -f "$REQ" ]; then
    echo "[sourceme] Installing requirements.txt ..."
    pip install -r "$REQ"
else
    echo "[sourceme] WARNING: requirements.txt not found - skipping install."
fi

echo ""
echo "[sourceme] Environment ready. Python: $(python --version)"
echo "   Run:  python scripts/gold_notifier.py --dry-run"
