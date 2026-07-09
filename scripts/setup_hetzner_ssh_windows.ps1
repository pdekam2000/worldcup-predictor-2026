#!/usr/bin/env pwsh
# Phase 1 — Windows SSH key + config scaffold for Hetzner deploy user (LOCAL ONLY).
# Does NOT connect to the server. Does NOT store passwords.

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$HostName,
    [int]$Port = 22,
    [string]$User = "deploy",
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) { Write-Host $Message }
function Write-Warn([string]$Message) { Write-Warning $Message }

function Test-OpenSshAvailable {
    $ssh = Get-Command ssh -ErrorAction SilentlyContinue
    $keygen = Get-Command ssh-keygen -ErrorAction SilentlyContinue
    return (@($ssh, $keygen) | Where-Object { $_ -ne $null }).Count -eq 2
}

$sshDir = Join-Path $env:USERPROFILE ".ssh"
$privateKey = Join-Path $sshDir "worldcup_hetzner_ed25519"
$publicKey = "$privateKey.pub"
$configPath = Join-Path $sshDir "config"
$markerBegin = "# BEGIN worldcup-prod (managed by setup_hetzner_ssh_windows.ps1)"
$markerEnd = "# END worldcup-prod"

Write-Info "==> Phase 1 — Hetzner SSH scaffold (local only)"

if (-not (Test-OpenSshAvailable)) {
    Write-Warn "OpenSSH Client not found (ssh / ssh-keygen)."
    Write-Info "Install: Settings -> Apps -> Optional features -> Add OpenSSH Client"
    Write-Info "Or install OpenSSH Client via Windows Optional Features (Settings UI)"
    exit 2
}

if (-not $HostName) {
    $HostName = Read-Host "Enter Hetzner host (DNS name or IP for SSH config HostName — not saved elsewhere)"
}
if (-not $HostName.Trim()) {
    Write-Warn "HostName is required."
    exit 2
}

if (-not (Test-Path $sshDir)) {
    if ($PSCmdlet.ShouldProcess($sshDir, "Create .ssh directory")) {
        if (-not $DryRun) { New-Item -ItemType Directory -Path $sshDir -Force | Out-Null }
    }
}

$keyExists = Test-Path $privateKey
if ($keyExists -and -not $Force) {
    Write-Info "Existing private key preserved: $privateKey"
} elseif (-not $keyExists) {
    $comment = "worldcup-hetzner-deploy-$env:USERNAME@$(hostname)"
    $args = @("-t", "ed25519", "-f", $privateKey, "-C", $comment, "-N", "")
    if ($PSCmdlet.ShouldProcess($privateKey, "Generate ED25519 key")) {
        if (-not $DryRun) {
            & ssh-keygen @args | Out-Host
        } else {
            Write-Info "[DryRun] ssh-keygen -t ed25519 -f $privateKey -C $comment -N ''"
        }
    }
} else {
    Write-Warn "Private key exists; -Force ignored for safety (never overwrite private key)."
}

if (-not $DryRun -and -not (Test-Path $publicKey)) {
    Write-Warn "Public key not found at $publicKey — generate key first."
    exit 2
}

$block = @"
$markerBegin
Host worldcup-prod
    HostName $($HostName.Trim())
    User $User
    Port $Port
    IdentityFile ~/.ssh/worldcup_hetzner_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
$markerEnd
"@

$existing = ""
if (Test-Path $configPath) {
    $existing = Get-Content -Raw -Path $configPath -ErrorAction SilentlyContinue
    if ($null -eq $existing) { $existing = "" }
}

$newConfig = $existing
if ($existing -match [regex]::Escape($markerBegin)) {
    $pattern = "(?s)$([regex]::Escape($markerBegin)).*?$([regex]::Escape($markerEnd))\r?\n?"
    $newConfig = [regex]::Replace($existing, $pattern, ($block.TrimEnd() + "`n"))
    Write-Info "Updated existing worldcup-prod SSH config block (idempotent)."
} elseif ($existing -match "(?m)^Host\s+worldcup-prod\b") {
    $pattern = "(?s)(?m)^Host\s+worldcup-prod\b.*?(?=\r?\nHost\s+|\z)"
    $newConfig = [regex]::Replace($existing, $pattern, ($block.TrimEnd() + "`n"), 1)
    Write-Info "Replaced legacy Host worldcup-prod block."
} else {
    if ($existing -and -not $existing.EndsWith("`n")) { $existing += "`n" }
    $newConfig = $existing + $block.TrimEnd() + "`n"
    Write-Info "Appended worldcup-prod SSH config block."
}

if ($PSCmdlet.ShouldProcess($configPath, "Write SSH config")) {
    if (-not $DryRun) {
        if (Test-Path $configPath) {
            $backup = "$configPath.bak.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Copy-Item -Path $configPath -Destination $backup -Force
            Write-Info "SSH config backup: $backup"
        }
        Set-Content -Path $configPath -Value $newConfig -Encoding utf8NoBOM
        icacls $configPath /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null
    } else {
        Write-Info "[DryRun] Would write SSH config to $configPath"
    }
}

Write-Info ""
Write-Info "=== Summary ==="
Write-Info "Private key : $privateKey"
Write-Info "Public key  : $publicKey"
Write-Info "SSH alias   : worldcup-prod"
Write-Info ""
if (Test-Path $publicKey) {
    Write-Info "=== Public key (install on server for deploy user) ==="
    Get-Content $publicKey | Write-Host
} elseif ($DryRun) {
    Write-Info "[DryRun] Public key will be at $publicKey after key generation."
}
Write-Info ""
Write-Info "Next manual steps:"
Write-Info "  1. Run bootstrap on server as admin (after review): scripts/bootstrap_hetzner_deploy_user.sh"
Write-Info "  2. Test in a NEW terminal: ssh worldcup-prod"
Write-Info "  3. Do NOT close your existing admin session until key login is confirmed."
Write-Info ""
Write-Info "This script did NOT connect to Hetzner."
