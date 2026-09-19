#Requires -Version 5.1
<#
.SYNOPSIS
  Registers the NotionHub Native Messaging host with Chrome / Edge / Chromium.

.DESCRIPTION
  Creates native\com.notionhub.host.json (path + allowed extension id) and writes
  the HKCU registry key each Chromium browser reads to discover native hosts.

  The host lets the extension panel write the project .env and run
  `notionhub sync` directly, so no manual copy/paste is needed.

.PARAMETER ExtensionId
  Browser extension id. Auto-detected from the local Edge/Chrome profile when
  omitted (looks for an unpacked extension named "NotionHub").

.PARAMETER EnvFile
  Absolute path of the .env the host manages. Defaults to <repo>\.env

.PARAMETER Cli
  Command used to run the sync. Defaults to "notionhub".

.PARAMETER PythonPath
  Python interpreter used to launch the host. Auto-detected (pythonw preferred,
  so no console window flashes).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File native\install.ps1
#>
[CmdletBinding()]
param(
  [string] $ExtensionId,
  [string] $EnvFile,
  [string] $Cli = "notionhub"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$nativeDir = Join-Path $repoRoot "native"
$bridgeExe = Join-Path $nativeDir "NotionHubBridge.exe"
$manifestPath = Join-Path $nativeDir "com.notionhub.host.json"

if (-not $EnvFile) { $EnvFile = Join-Path $repoRoot ".env" }

# The bridge is a self-contained native EXE (no Python at runtime). If it is
# missing we compile it on the fly with the .NET Framework csc that ships with
# Windows, so the install never depends on a pre-built binary.
# Rebuild whenever a source file is newer than the binary, otherwise an edited
# Bridge.cs would be silently ignored and the panel would keep talking to a
# stale host (e.g. missing the worker_* commands).
function Test-BridgeStale {
  if (-not (Test-Path $bridgeExe)) { return $true }
  $exeTime = (Get-Item $bridgeExe).LastWriteTimeUtc
  foreach ($src in @("Bridge.cs", "Json.cs")) {
    $p = Join-Path $nativeDir $src
    if (Test-Path $p) {
      if ((Get-Item $p).LastWriteTimeUtc -gt $exeTime) { return $true }
    }
  }
  return $false
}

if (Test-BridgeStale) {
  Write-Host "Bridge EXE missing or out of date; compiling from source..." -ForegroundColor Yellow
  if (-not (Test-Path (Join-Path $nativeDir "Bridge.cs"))) {
    throw "not found: Bridge.cs and NotionHubBridge.exe"
  }
  $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
  if (-not (Test-Path $csc)) {
    $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe"
  }
  if (-not (Test-Path $csc)) { throw ".NET Framework 4 csc.exe not found" }
  & $csc /nologo /target:winexe /platform:anycpu /out:$bridgeExe `
    (Join-Path $nativeDir "Bridge.cs") (Join-Path $nativeDir "Json.cs")
  if (-not (Test-Path $bridgeExe)) { throw "compile failed: $bridgeExe" }
  Write-Host "Compiled    : $bridgeExe" -ForegroundColor Green
}

# The package registers two entry points; prefer whichever is actually on PATH.
if ($Cli -eq "notionhub") {
  if (-not (Get-Command notionhub -ErrorAction SilentlyContinue)) {
    if (Get-Command weread2notion -ErrorAction SilentlyContinue) {
      Write-Host "'notionhub' not on PATH, falling back to 'weread2notion'" -ForegroundColor Yellow
      $Cli = "weread2notion"
    } else {
      Write-Warning "Neither 'notionhub' nor 'weread2notion' is on PATH. Run 'pip install -e .' first, or the sync button will fail."
    }
  }
}

# Resolve the CLI to its absolute path. The native host is launched by the
# browser with a reduced PATH, so a bare command name can fail to start even
# though it works in an interactive shell. Resolve it while we still have the
# full PATH so the manifest records the full executable path.
$resolvedCli = (Get-Command $Cli -ErrorAction SilentlyContinue).Source
if ($resolvedCli) {
  $Cli = $resolvedCli
  Write-Host "CLI resolved : $Cli" -ForegroundColor Cyan
}

# ---------------- Extension id ----------------
# Unpacked extensions ("Load unpacked") are NOT copied into <Profile>\Extensions,
# so we must read the profile's (Secure) Preferences and match on the load path.
function Get-ProfileDirs {
  $bases = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\Edge\User Data"),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data"),
    (Join-Path $env:LOCALAPPDATA "Chromium\User Data")
  )
  foreach ($base in $bases) {
    if (-not (Test-Path $base)) { continue }
    Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match '^(Default|Profile \d+)$' }
  }
}

function Find-UnpackedExtensionId {
  $root = (Resolve-Path $repoRoot).Path.TrimEnd('\')
  foreach ($profile in Get-ProfileDirs) {
    foreach ($file in @("Secure Preferences", "Preferences")) {
      $path = Join-Path $profile.FullName $file
      if (-not (Test-Path $path)) { continue }
      try { $json = Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
      if (-not $json.extensions -or -not $json.extensions.settings) { continue }
      foreach ($prop in $json.extensions.settings.PSObject.Properties) {
        $candidate = $prop.Value.path
        if (-not $candidate) { continue }
        if ($candidate.Replace('/', '\').TrimEnd('\') -ieq $root) {
          return $prop.Name
        }
      }
    }
  }
  return $null
}

function Find-PackedExtensionId {
  foreach ($profile in Get-ProfileDirs) {
    $extDir = Join-Path $profile.FullName "Extensions"
    if (-not (Test-Path $extDir)) { continue }
    foreach ($manifest in Get-ChildItem -Path $extDir -Filter manifest.json -Recurse -ErrorAction SilentlyContinue) {
      try { $json = Get-Content $manifest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
      # Case-sensitive: a store extension named "Notionhub" is NOT this project.
      if ($json.name -ceq "NotionHub") {
        return $manifest.Directory.Parent.Name
      }
    }
  }
  return $null
}

function Find-ExtensionId {
  $id = Find-UnpackedExtensionId
  if ($id) { return $id }
  return Find-PackedExtensionId
}

if (-not $ExtensionId) { $ExtensionId = Find-ExtensionId }
if (-not $ExtensionId) {
  Write-Warning "Extension id not detected. Load the unpacked extension first, then re-run with -ExtensionId <id>."
  Write-Warning "You can copy the id from edge://extensions/ (Developer mode)."
  $ExtensionId = Read-Host "Extension id (leave empty to abort)"
  if (-not $ExtensionId) { throw "aborted: no extension id" }
}
Write-Host "Extension id : $ExtensionId" -ForegroundColor Cyan

# ---------------- Host manifest ----------------
$manifest = [ordered]@{
  name            = "com.notionhub.host"
  description     = "NotionHub bridge: manage the project .env and run notionhub sync"
  path            = (Resolve-Path $bridgeExe).Path
  type            = "stdio"
  allowed_origins = @("chrome-extension://$ExtensionId/")
  args            = @(
    "--env-file",
    $EnvFile,
    "--cli",
    $Cli
  )
}
# Write without BOM: Chrome's manifest parser rejects a UTF-8 BOM.
$json = $manifest | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText(
  $manifestPath,
  $json,
  (New-Object System.Text.UTF8Encoding($false))
)
Write-Host "Host manifest: $manifestPath" -ForegroundColor Cyan
Write-Host "Bridge EXE   : $bridgeExe" -ForegroundColor Cyan
Write-Host "Env file     : $EnvFile" -ForegroundColor Cyan
Write-Host "CLI          : $Cli" -ForegroundColor Cyan

# ---------------- Registry ----------------
$keys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.notionhub.host",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.notionhub.host",
  "HKCU:\Software\Chromium\NativeMessagingHosts\com.notionhub.host"
)
foreach ($key in $keys) {
  New-Item -Path $key -Force | Out-Null
  Set-ItemProperty -Path $key -Name "(default)" -Value $manifestPath
  Write-Host "Registered   : $key" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. Reload the extension in edge://extensions/ and reopen the panel." -ForegroundColor Green
Write-Host "Open the panel: the config drawer should show a green bridge-connected status." -ForegroundColor Green
