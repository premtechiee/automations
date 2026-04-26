# SOURCEME.ps1 - dot-source this file to set up and activate the project venv
#
#   Usage (from the repo root in PowerShell):
#       . .\SOURCEME.ps1
#
# What it does:
#   1. Creates .venv with the current Python if it doesn't exist
#   2. Activates .venv in the current shell session
#   3. Upgrades pip silently
#   4. Installs / syncs requirements.txt

$ErrorActionPreference = "Stop"

$ROOT = $PSScriptRoot
$VENV = Join-Path $ROOT ".venv"
$REQ  = Join-Path $ROOT "requirements.txt"

# 1. Create venv
if (-not (Test-Path (Join-Path $VENV "Scripts\python.exe"))) {
    Write-Host "[SOURCEME] Creating virtual environment at .venv ..." -ForegroundColor Cyan
    python -m venv $VENV
} else {
    Write-Host "[SOURCEME] .venv already exists - skipping creation." -ForegroundColor DarkGray
}

# 2. Activate
$activate = Join-Path $VENV "Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "[SOURCEME] Activation script not found: $activate"
    return
}
Write-Host "[SOURCEME] Activating .venv ..." -ForegroundColor Cyan
. $activate

# 3. Upgrade pip
Write-Host "[SOURCEME] Upgrading pip ..." -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet

# 4. Install dependencies
if (Test-Path $REQ) {
    Write-Host "[SOURCEME] Installing requirements.txt ..." -ForegroundColor Cyan
    pip install -r $REQ
} else {
    Write-Warning "[SOURCEME] requirements.txt not found - skipping install."
}

Write-Host ""
Write-Host "[SOURCEME] Environment ready. Python: $(python --version)" -ForegroundColor Green
Write-Host "   Run:  python scripts/gold_notifier.py --dry-run" -ForegroundColor DarkGray

$env:ANGEL_API_KEY      = 'TFc6IfAs'
$env:ANGEL_CLIENT_CODE  = 'AAAD884268'
$env:ANGEL_MPIN         = '1994'
$env:ANGEL_TOTP_SECRET  = 'K2JYXK646JV64TTYB6XQEQO4BQ'
$env:ANGEL_TRADING_ENABLED = '0'