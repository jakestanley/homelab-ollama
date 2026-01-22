$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
  Write-Error "Missing virtualenv at .venv. Create it with: python -m venv .venv"
}

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
  Write-Warning "Missing .env file; copy .env.example and update SERVICE_PORT."
}

& $venvPython (Join-Path $root "app.py")
