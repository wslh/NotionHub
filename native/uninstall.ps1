#Requires -Version 5.1
<#
.SYNOPSIS
  Removes the NotionHub Native Messaging host registration.
#>
[CmdletBinding()]
param()

$keys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.notionhub.host",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.notionhub.host",
  "HKCU:\Software\Chromium\NativeMessagingHosts\com.notionhub.host"
)
foreach ($key in $keys) {
  if (Test-Path $key) {
    Remove-Item -Path $key -Recurse -Force
    Write-Host "Removed: $key" -ForegroundColor Yellow
  }
}
Write-Host "Done. The panel falls back to clipboard-only mode." -ForegroundColor Green
