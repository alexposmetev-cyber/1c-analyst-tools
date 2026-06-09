#Requires -Version 5.1
<#
.SYNOPSIS
    Ставит тестовый job в очередь оркестратора и ждёт результат.
#>
param(
    [string]$OrchestratorUrl = 'http://127.0.0.1:8787',
    [string]$BridgeId = 'demotrd',
    [string]$BridgeToken = 'change-me-local-demo-token',
    [string]$Tool = 'execute_query',
    [string]$Query = '',
    [int]$WaitSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$arguments = @{}
if ($Tool -eq 'execute_query') {
    if (-not $Query.Trim()) {
        $Query = (& "$PSScriptRoot\..\mcp\.venv\Scripts\python.exe" -c "print('\u0412\u042b\u0411\u0420\u0410\u0422\u042c 1 \u041a\u0410\u041a N')")
    }
    $arguments = @{
        query = $Query
        max_rows = 10
    }
}

$body = @{
    bridge_id = $BridgeId
    bridge_token = $BridgeToken
    tool = $Tool
    arguments = $arguments
} | ConvertTo-Json -Depth 5 -Compress

$enqueueUri = "$($OrchestratorUrl.TrimEnd('/'))/api/bridge/enqueue"
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$queued = Invoke-RestMethod -Method Post -Uri $enqueueUri -Body $bodyBytes -ContentType 'application/json; charset=utf-8'
$jobId = $queued.job_id
Write-Host "Queued job_id=$jobId"

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $jobUri = "$($OrchestratorUrl.TrimEnd('/'))/api/jobs/$jobId"
    $job = Invoke-RestMethod -Method Get -Uri $jobUri
    if ($job.status -in @('ok', 'error')) {
        $job | ConvertTo-Json -Depth 10
        exit $(if ($job.status -eq 'ok') { 0 } else { 1 })
    }
    Write-Host "status=$($job.status) ..."
}

Write-Error "Таймаут ожидания job $jobId. Агент запущен?"
exit 1
