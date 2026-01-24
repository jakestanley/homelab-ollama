param(
  [string]$ServiceName,
  [switch]$Start
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $ServiceName) {
  $ServiceName = Split-Path -Leaf $root
}

$displayName = "Homelab Ollama"
$description = "Controls local Ollama runtime via HTTP API"

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
  Write-Error "Missing virtualenv at .venv. Create it with: python -m venv .venv"
}

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) {
  Write-Error "Missing .env file. Copy .env.example to .env and set SERVICE_PORT."
}

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
  Write-Error "nssm not found in PATH. Install NSSM and retry."
}

$appPath = $venvPython
$appArgs = "`"$root\app.py`""

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -eq $service) {
  & nssm install $ServiceName $appPath $appArgs | Out-Null
}

& nssm set $ServiceName DisplayName $displayName | Out-Null
& nssm set $ServiceName Description $description | Out-Null
& nssm set $ServiceName AppDirectory $root | Out-Null

$logsDir = Join-Path $root "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
& nssm set $ServiceName AppStdout (Join-Path $logsDir "$ServiceName-stdout.log") | Out-Null
& nssm set $ServiceName AppStderr (Join-Path $logsDir "$ServiceName-stderr.log") | Out-Null

$envLines = Get-Content -Path $envFile | Where-Object {
  $_ -and $_ -notmatch '^\s*#'
}


# Auto-detect OLLAMA_EXE if not set (service PATH may differ from your shell).
$envLines = @($envLines)
$hasOllamaExe = $envLines | Where-Object { $_ -match "^OLLAMA_EXE=" }
if (-not $hasOllamaExe) {
  $cmd = Get-Command ollama.exe -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source) {
    $envLines = @("OLLAMA_EXE=$($cmd.Source)") + $envLines
  } else {
    Write-Warning "OLLAMA_EXE is not set and ollama.exe was not found on PATH. Set OLLAMA_EXE in .env to a full path."
  }
}
if ($envLines) {
  # Store each VAR=VALUE as a separate multi-string entry
  & nssm set $ServiceName AppEnvironmentExtra @($envLines) | Out-Null
}

if ($Start) {
  & nssm restart $ServiceName | Out-Null
  if ($LASTEXITCODE -ne 0) {
    & nssm start $ServiceName | Out-Null
  }
}

Write-Host "Installed/updated NSSM service: $ServiceName"
