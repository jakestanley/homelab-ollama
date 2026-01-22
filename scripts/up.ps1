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

$repoName = Split-Path -Leaf $root

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

  function Test-PortMatch {
    param(
      [string]$LocalPort,
      [string]$TargetPort
    )

    if (-not $LocalPort -or $LocalPort -eq "Any") {
      return $false
    }

    if ($LocalPort -eq $TargetPort) {
      return $true
    }

    if ($LocalPort -match ',') {
      foreach ($part in ($LocalPort -split ',')) {
        if (Test-PortMatch -LocalPort $part.Trim() -TargetPort $TargetPort) {
          return $true
        }
      }
    }

    if ($LocalPort -match '^\d+-\d+$') {
      $bounds = $LocalPort -split '-'
      $start = [int]$bounds[0]
      $end = [int]$bounds[1]
      $value = [int]$TargetPort
      if ($value -ge $start -and $value -le $end) {
        return $true
      }
    }

    return $false
  }

  $portFilters = Get-NetFirewallPortFilter -Protocol TCP -ErrorAction SilentlyContinue | Where-Object {
    Test-PortMatch -LocalPort $_.LocalPort -TargetPort $Port
  }
  if (-not $portFilters) {
    return $false
  }

  $rules = Get-NetFirewallRule -AssociatedNetFirewallPortFilter $portFilters -ErrorAction SilentlyContinue
  foreach ($rule in $rules) {
    if ($rule.Direction -ne "Inbound") {
      continue
    }

    if ($rule.Profile -eq "Any" -or $rule.Profile -match "Private") {
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
  $ruleName = "$repoName ($servicePort)"
  $firewallCommand = "New-NetFirewallRule -DisplayName `"$ruleName`" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $servicePort -Profile Private"

  if (-not (Test-IsAdministrator)) {
    Write-Warning "Not running elevated; Windows Firewall rule not ensured."
    Write-Host "Run in an elevated PowerShell to create the inbound rule:"
    Write-Host $firewallCommand
  } else {
    if (-not (Test-PrivateTcpFirewallRuleExists -Port $servicePort)) {
      New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $servicePort -Profile Private | Out-Null
    }
  }
} else {
  Write-Warning "SERVICE_PORT is not set; skipping Windows Firewall rule check."
}

& $venvPython (Join-Path $root "app.py")
