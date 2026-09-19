$ErrorActionPreference = "Stop"
# 动态推导：仓库目录可能改名（例如 weread2notion-AI → NotionHub），
# 硬编码绝对路径会让注册指向已不存在的位置，本机同步随之失效。
$manifest = Join-Path $PSScriptRoot "com.notionhub.host.json"
if (-not (Test-Path $manifest)) { throw "not found: $manifest" }
$keys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.notionhub.host",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.notionhub.host",
  "HKCU:\Software\Chromium\NativeMessagingHosts\com.notionhub.host"
)
foreach ($k in $keys) {
  New-Item -Path $k -Force | Out-Null
  Set-ItemProperty -Path $k -Name "(default)" -Value $manifest
  Write-Host "Registered: $k"
}
Write-Host "Done."
