#Requires -Version 5.1
<#
.SYNOPSIS
    Zapuskaet orchestrator i Bridge Agent, esli eshche ne rabotayut.

.DESCRIPTION
    Vyzyvaetsya iz Start-OpenCode i pri starte MCP onec-data.
    Bez bridge/agent/bridge-agent.json - tihij propusk.
#>
[CmdletBinding()]
param(
    [switch]$Quiet,
    [int]$OrchestratorWaitSec = 20,
    [int]$AgentWaitSec = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$ConfigPath = Join-Path $ProjectRoot 'bridge\agent\bridge-agent.json'
$OrchestratorUrl = 'http://127.0.0.1:8787'
$AgentStaleSec = 90

function Write-BridgeInfo {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Get-BridgeConfig {
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        return $null
    }
    try {
        $raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
        return $raw | ConvertFrom-Json
    }
    catch {
        Write-BridgeInfo ("Bridge: config read error: " + $_.Exception.Message)
        return $null
    }
}

function Test-OrchestratorHealthy {
    try {
        $response = Invoke-WebRequest -Uri ($OrchestratorUrl + '/health') -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ne 200) {
            return $false
        }
        $payload = $response.Content | ConvertFrom-Json
        return ($payload.status -eq 'ok')
    }
    catch {
        return $false
    }
}

function Test-BridgeAgentOnline {
    param([string]$BridgeId)

    if (-not $BridgeId) {
        return $false
    }

    try {
        $payload = Invoke-RestMethod -Uri ($OrchestratorUrl + '/api/bridges') -TimeoutSec 5
        $bridges = @($payload.bridges)
        foreach ($item in $bridges) {
            if ([string]$item.bridge_id -ne $BridgeId) {
                continue
            }
            $lastPoll = $item.last_poll_at
            if ($null -eq $lastPoll) {
                return $false
            }
            $epoch = [datetime]'1970-01-01T00:00:00Z'
            $now = ([datetime]::UtcNow - $epoch).TotalSeconds
            return (($now - [double]$lastPoll) -le $AgentStaleSec)
        }
        return $false
    }
    catch {
        return $false
    }
}

function Start-DetachedCmd {
    param(
        [string]$Title,
        [string]$CmdPath
    )

    if (-not (Test-Path -LiteralPath $CmdPath)) {
        throw ("Not found: " + $CmdPath)
    }

    Start-Process -FilePath $CmdPath -WorkingDirectory $ProjectRoot -WindowStyle Minimized | Out-Null
    Write-BridgeInfo ("Bridge: started " + $Title)
}

function Wait-Until {
    param(
        [scriptblock]$Predicate,
        [int]$TimeoutSec,
        [int]$IntervalMs = 500
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (& $Predicate) {
            return $true
        }
        Start-Sleep -Milliseconds $IntervalMs
    }
    return $false
}

$config = Get-BridgeConfig
if (-not $config) {
    if (-not $Quiet) {
        Write-BridgeInfo 'Bridge: bridge-agent.json not found, using COM fallback.'
    }
    return @{
        configured = $false
        ready      = $false
    }
}

$bridgeId = [string]$config.bridge_id
if ($config.orchestrator_url) {
    $OrchestratorUrl = [string]$config.orchestrator_url
    $OrchestratorUrl = $OrchestratorUrl.TrimEnd('/')
}

$result = [ordered]@{
    configured     = $true
    orchestratorOk = $false
    agentOnline    = $false
    ready          = $false
}

if (-not (Test-OrchestratorHealthy)) {
    $orchCmd = Join-Path $ProjectRoot 'bridge\Start-Orchestrator.cmd'
    Start-DetachedCmd -Title 'orchestrator' -CmdPath $orchCmd
    $orchReady = Wait-Until -Predicate { Test-OrchestratorHealthy } -TimeoutSec $OrchestratorWaitSec
    if (-not $orchReady) {
        Write-BridgeInfo 'Bridge: orchestrator health timeout.'
        return $result
    }
}

$result.orchestratorOk = $true

if (-not (Test-BridgeAgentOnline -BridgeId $bridgeId)) {
    $agentCmd = Join-Path $ProjectRoot 'bridge\Start-BridgeAgent.cmd'
    Start-DetachedCmd -Title 'agent' -CmdPath $agentCmd
    $agentReady = Wait-Until -Predicate { Test-BridgeAgentOnline -BridgeId $bridgeId } -TimeoutSec $AgentWaitSec
    if (-not $agentReady) {
        Write-BridgeInfo 'Bridge: agent poll timeout.'
        return $result
    }
}

$result.agentOnline = $true
$result.ready = $true
Write-BridgeInfo 'Bridge: ready for onec_query.'
return $result
