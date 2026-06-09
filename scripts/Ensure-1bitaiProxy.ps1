#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $ProjectRoot 'mcp\.venv\Scripts\python.exe'
# Относительный путь: абсолютный с пробелами (например «старый ноут») ломает ArgumentList у Start-Process
$ProxyRelative = 'scripts\1bitai_proxy.py'
$Port = 18765

if (-not (Test-Path -LiteralPath $Python)) {
    throw "MCP venv не найден: $Python. Запустите scripts\Setup-Mcp.ps1"
}

function Get-1bitApiKey {
    if ($env:ONEBITAI_API_KEY) {
        return $env:ONEBITAI_API_KEY.Trim()
    }
    $savedKey = [System.Environment]::GetEnvironmentVariable('ONEBITAI_API_KEY', 'User')
    if ($savedKey) {
        return $savedKey.Trim()
    }
    $localConfig = Join-Path $ProjectRoot 'opencode.local.json'
    if (-not (Test-Path -LiteralPath $localConfig)) {
        return ''
    }
    try {
        $json = Get-Content -LiteralPath $localConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        $key = [string]$json.provider.'1bitai'.options.apiKey
        if ($key -and -not $key.StartsWith('{env:')) {
            return $key.Trim()
        }
    }
    catch {
        return ''
    }
    return ''
}

$resolvedKey = Get-1bitApiKey
if ($resolvedKey) {
    $env:ONEBITAI_API_KEY = $resolvedKey
}

function Stop-ProxyOnPort {
    param([int]$ListenPort)
    $lines = netstat -ano | Select-String ":$ListenPort\s+.*LISTENING"
    foreach ($line in $lines) {
        $parts = ($line -split '\s+') | Where-Object { $_ -ne '' }
        if ($parts.Count -ge 5) {
            $processId = [int]$parts[-1]
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-ProxyPort {
    param([int]$ListenPort)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect('127.0.0.1', $ListenPort, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(500)
        if ($ok -and $client.Connected) {
            $client.Close()
            return $true
        }
        $client.Close()
    }
    catch {
        return $false
    }
    return $false
}

Stop-ProxyOnPort -ListenPort $Port
Start-Sleep -Milliseconds 300

$logDir = Join-Path $ProjectRoot 'output'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logOut = Join-Path $logDir '1bitai-proxy.out.log'
$logErr = Join-Path $logDir '1bitai-proxy.err.log'

$proxyProcess = Start-Process `
    -FilePath $Python `
    -ArgumentList $ProxyRelative `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -PassThru

$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline) {
    if ($proxyProcess.HasExited) {
        $tail = @()
        foreach ($logPath in @($logErr, $logOut)) {
            if (Test-Path -LiteralPath $logPath) {
                $tail += Get-Content -LiteralPath $logPath -Tail 10 -ErrorAction SilentlyContinue
            }
        }
        throw "Прокси завершился (код $($proxyProcess.ExitCode)). Лог:`n$($tail -join [Environment]::NewLine)"
    }
    if (Test-ProxyPort -ListenPort $Port) {
        Write-Host "Прокси 1bit AI: http://127.0.0.1:$Port/v1 (PID $($proxyProcess.Id))"
        return
    }
    Start-Sleep -Milliseconds 400
}

Stop-Process -Id $proxyProcess.Id -Force -ErrorAction SilentlyContinue
throw "Прокси не поднялся на порту $Port за 15 с. См. $logErr"
