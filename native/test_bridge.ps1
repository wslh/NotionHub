$ErrorActionPreference = "Stop"

# Locate the bridge EXE and the repo .env without any Chinese literal in code.
$exe = Get-ChildItem -Path $env:USERPROFILE\Desktop -Filter NotionHubBridge.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $exe) { Write-Host "EXE_NOT_FOUND"; exit 1 }
$repo = $exe.Directory.Parent.FullName
$envFile = Join-Path $repo ".env"
Write-Host ("EXE = " + $exe.FullName)
Write-Host ("ENV = " + $envFile)

function Send-Frame($proc, $obj) {
    $json = [System.Text.Encoding]::UTF8.GetBytes($obj)
    $hdr = [BitConverter]::GetBytes([uint32]$json.Length)
    $proc.StandardInput.BaseStream.Write($hdr, 0, 4)
    $proc.StandardInput.BaseStream.Write($json, 0, $json.Length)
    $proc.StandardInput.BaseStream.Flush()
}

function Read-Frame($proc) {
    $stm = $proc.StandardOutput.BaseStream
    $hdr = New-Object byte[] 4
    $got = 0
    while ($got -lt 4) {
        $n = $stm.Read($hdr, $got, 4 - $got)
        if ($n -le 0) { return $null }
        $got += $n
    }
    $len = [BitConverter]::ToUInt32($hdr, 0)
    $buf = New-Object byte[] $len
    $got = 0
    while ($got -lt $len) {
        $n = $stm.Read($buf, $got, $len - $got)
        if ($n -le 0) { return $null }
        $got += $n
    }
    return [System.Text.Encoding]::UTF8.GetString($buf, 0, $got)
}

$p = New-Object System.Diagnostics.Process
$p.StartInfo.FileName = $exe.FullName
$p.StartInfo.Arguments = ('--env-file "' + $envFile + '" --cli weread2notion')
$p.StartInfo.UseShellExecute = $false
$p.StartInfo.RedirectStandardInput = $true
$p.StartInfo.RedirectStandardOutput = $true
$p.StartInfo.CreateNoWindow = $true
$p.Start() | Out-Null

function Test-Case($label, $msg) {
    Send-Frame $p $msg
    Start-Sleep -Milliseconds 300
    $resp = Read-Frame $p
    Write-Host ("`n=== $label ===")
    Write-Host ($resp)
}

Test-Case "ping"      '{"type":"ping"}'
Test-Case "env_read"  '{"type":"env_read"}'
Test-Case "sync_log"  '{"type":"sync_log","lines":20}'

$p.StandardInput.Close()
if (-not $p.WaitForExit(3000)) { $p.Kill() }
Write-Host "`nDONE"
