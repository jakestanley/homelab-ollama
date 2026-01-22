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

function Get-EnvValue {
  param(
    [string]$Path,
    [string]$Key
  )

  if (-not (Test-Path $Path)) {
    return $null
  }

  foreach ($line in Get-Content -Path $Path) {
    if ($line -match '^\s*#') { continue }
    if ($line -match '^\s*$') { continue }
    if ($line -match "^\s*${Key}\s*=\s*(.+)\s*$") {
      return $Matches[1].Trim()
    }
  }

  return $null
}

function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-PrivateTcpFirewallRuleExists {
  param(
    [string]$Port
  )

  $rules = Get-NetFirewallRule -Direction Inbound -ErrorAction SilentlyContinue | Where-Object {
    $_.Profile -eq "Any" -or $_.Profile -match "Private"
  }

  foreach ($rule in $rules) {
    $portFilter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule -ErrorAction SilentlyContinue
    if ($null -eq $portFilter) {
      continue
    }

    if ($portFilter.Protocol -eq "TCP" -and $portFilter.LocalPort -eq $Port) {
      return $true
    }
  }

  return $false
}

$servicePort = Get-EnvValue -Path $envFile -Key "SERVICE_PORT"
if (-not $servicePort -and $env:SERVICE_PORT) {
  $servicePort = $env:SERVICE_PORT
}

if ($servicePort) {
  $firewallCommand = "New-NetFirewallRule -DisplayName `"homelab-ollama ($servicePort)`" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $servicePort -Profile Private"

  if (-not (Test-IsAdministrator)) {
    Write-Warning "Not running elevated; Windows Firewall rule not ensured."
    Write-Host "Run in an elevated PowerShell to create the inbound rule:"
    Write-Host $firewallCommand
  } else {
    if (-not (Test-PrivateTcpFirewallRuleExists -Port $servicePort)) {
      New-NetFirewallRule -DisplayName "homelab-ollama ($servicePort)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $servicePort -Profile Private | Out-Null
    }
  }
} else {
  Write-Warning "SERVICE_PORT is not set; skipping Windows Firewall rule check."
}

& $venvPython (Join-Path $root "app.py")
