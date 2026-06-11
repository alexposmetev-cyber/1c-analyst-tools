#Requires -Version 5.1
<#
.SYNOPSIS
    1C Bridge Agent — долгоживущий COM-мост к оркестратору (poll/result).

.PARAMETER ConfigPath
    Путь к bridge-agent.json (по умолчанию рядом со скриптом).
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'bridge-agent.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# stdout/stderr в UTF-8: PS 5.1 по умолчанию пишет в OEM (cp866),
# а Python читает поток как UTF-8.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

. (Join-Path $PSScriptRoot 'BridgeCom.ps1')

function Write-BridgeLog {
    param([string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$stamp] $Message"
}

function Read-BridgeAgentConfig {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Конфиг не найден: $Path. Скопируйте bridge-agent.json.example в bridge-agent.json."
    }

    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $config = $raw | ConvertFrom-Json
    return $config
}

function Get-BridgeConnectionHashtable {
    param($Config)

    $conn = $Config.connection
    if (-not $conn) {
        throw 'В конфиге отсутствует секция connection.'
    }

    return @{
        info_base_path = [string]($conn.info_base_path)
        info_base_name = [string]($conn.info_base_name)
        server = [string]($conn.server)
        ref = [string]($conn.ref)
        user = [string]($conn.user)
        password = [string]($conn.password)
    }
}

function ConvertFrom-BridgeUtf8Json {
    param([string]$Text)
    return $Text | ConvertFrom-Json
}

function Get-BridgeWebResponseUtf8Text {
    param(
        [Parameter(Mandatory = $true)]
        $Response
    )

    if ($null -ne $Response.RawContentStream) {
        $stream = $Response.RawContentStream
        if ($stream.CanSeek) {
            $stream.Position = 0
        }
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        return $reader.ReadToEnd()
    }

    $bytes = [System.Text.Encoding]::GetEncoding('ISO-8859-1').GetBytes([string]$Response.Content)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Invoke-BridgeWebJson {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('Get', 'Post')]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [string]$BodyJson = '',
        [int]$TimeoutSec = 120,
        [hashtable]$Headers = @{}
    )

    if ($Method -eq 'Get') {
        $response = Invoke-WebRequest -Uri $Uri -Method Get -Headers $Headers `
            -UseBasicParsing -TimeoutSec $TimeoutSec
    }
    else {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($BodyJson)
        $response = Invoke-WebRequest -Uri $Uri -Method Post -Body $bytes `
            -Headers $Headers -ContentType 'application/json; charset=utf-8' `
            -UseBasicParsing -TimeoutSec $TimeoutSec
    }

    $text = Get-BridgeWebResponseUtf8Text -Response $response
    return ConvertFrom-BridgeUtf8Json -Text $text
}

function Invoke-BridgeOrchestratorPoll {
    param(
        [string]$BaseUrl,
        [string]$BridgeId,
        [string]$BridgeToken,
        [int]$WaitSec
    )

    $uri = '{0}/api/bridge/poll?bridge_id={1}&wait_sec={2}' -f `
        $BaseUrl.TrimEnd('/'), `
        [uri]::EscapeDataString($BridgeId), `
        $WaitSec

    return Invoke-BridgeWebJson -Method Get -Uri $uri `
        -Headers @{ 'X-Bridge-Token' = $BridgeToken } `
        -TimeoutSec ($WaitSec + 15)
}

function Submit-BridgeJobResult {
    param(
        [string]$BaseUrl,
        [string]$BridgeId,
        [string]$BridgeToken,
        [string]$JobId,
        [string]$Status,
        $Result,
        [string]$ErrorMessage
    )

    $body = @{
        job_id = $JobId
        bridge_id = $BridgeId
        bridge_token = $BridgeToken
        status = $Status
        result = $Result
        error = $ErrorMessage
    }

    $uri = '{0}/api/bridge/result' -f $BaseUrl.TrimEnd('/')
    $json = $body | ConvertTo-Json -Depth 10 -Compress
    return Invoke-BridgeWebJson -Method Post -Uri $uri -BodyJson $json
}

function Invoke-BridgeTool {
    param(
        [hashtable]$ConnectionConfig,
        [string]$ToolName,
        [hashtable]$Arguments,
        [int]$DefaultMaxRows,
        [string]$PlatformPath
    )

    switch ($ToolName) {
        'ping' {
            Invoke-BridgeComWithReconnect -ConnectionConfig $ConnectionConfig -PlatformPath $PlatformPath -Action {
                param($Connection)
                $data = Invoke-BridgeComQuery -Connection $Connection -QueryText 'ВЫБРАТЬ 1 КАК N' -MaxRows 1
                return @{
                    tool = 'ping'
                    connected = $true
                    rows = $data.rows
                }
            }
        }
        'execute_query' {
            $query = [string]$Arguments.query
            if (-not $query.Trim()) {
                throw 'arguments.query не может быть пустым.'
            }
            $maxRows = $DefaultMaxRows
            if ($Arguments.ContainsKey('max_rows') -and $Arguments.max_rows) {
                $maxRows = [int]$Arguments.max_rows
            }
            if ($maxRows -lt 1) { $maxRows = 1 }
            if ($maxRows -gt 5000) { $maxRows = 5000 }

            Invoke-BridgeComWithReconnect -ConnectionConfig $ConnectionConfig -PlatformPath $PlatformPath -Action {
                param($Connection)
                $data = Invoke-BridgeComQuery -Connection $Connection -QueryText $query -MaxRows $maxRows
                return @{
                    tool = 'execute_query'
                    query = $query
                    rowCount = $data.rowCount
                    totalRows = $data.totalRows
                    columns = $data.columns
                    rows = $data.rows
                }
            }
        }
        default {
            throw "Неизвестный tool: $ToolName"
        }
    }
}

$config = Read-BridgeAgentConfig -Path $ConfigPath
$bridgeId = [string]$config.bridge_id
$bridgeToken = [string]$config.bridge_token
$orchestratorUrl = [string]$config.orchestrator_url
$pollIntervalSec = [int]($(if ($config.poll_interval_sec) { $config.poll_interval_sec } else { 2 }))
$pollWaitSec = [int]($(if ($config.poll_wait_sec) { $config.poll_wait_sec } else { 25 }))
$heartbeatSec = [int]($(if ($config.heartbeat_interval_sec) { $config.heartbeat_interval_sec } else { 60 }))
$queryMaxRows = [int]($(if ($config.query_max_rows) { $config.query_max_rows } else { 500 }))
$platformPath = [string]($(if ($config.platform_path) { $config.platform_path } else { '' }))
$connectionConfig = Get-BridgeConnectionHashtable -Config $config

if (-not $bridgeId -or -not $bridgeToken -or -not $orchestratorUrl) {
    throw 'bridge_id, bridge_token и orchestrator_url обязательны в bridge-agent.json.'
}

Write-BridgeLog "1C Bridge Agent: bridge_id=$bridgeId orchestrator=$orchestratorUrl"

try {
    $connectInfo = Connect-BridgeComSession -ConnectionConfig $connectionConfig -PlatformPath $platformPath
    Write-BridgeLog "COM подключён: $($connectInfo.progId) / $($connectInfo.platformVersion)"
}
catch {
    Write-BridgeLog "Ошибка первичного COM-подключения: $($_.Exception.Message)"
    throw
}

$lastHeartbeat = Get-Date
Write-BridgeLog 'Ожидание jobs (Ctrl+C для остановки)...'

while ($true) {
    try {
        if (((Get-Date) - $lastHeartbeat).TotalSeconds -ge $heartbeatSec) {
            Test-BridgeComHeartbeat | Out-Null
            $lastHeartbeat = Get-Date
            Write-BridgeLog 'Heartbeat OK'
        }

        $pollResponse = Invoke-BridgeOrchestratorPoll `
            -BaseUrl $orchestratorUrl `
            -BridgeId $bridgeId `
            -BridgeToken $bridgeToken `
            -WaitSec $pollWaitSec

        if (-not $pollResponse.job) {
            continue
        }

        $job = $pollResponse.job
        $jobId = [string]$job.job_id
        $tool = [string]$job.tool
        $argsHash = @{}
        if ($job.arguments) {
            $job.arguments.PSObject.Properties | ForEach-Object {
                $argsHash[$_.Name] = $_.Value
            }
        }

        Write-BridgeLog "Job $jobId tool=$tool"
        try {
            $result = Invoke-BridgeTool `
                -ConnectionConfig $connectionConfig `
                -ToolName $tool `
                -Arguments $argsHash `
                -DefaultMaxRows $queryMaxRows `
                -PlatformPath $platformPath

            Submit-BridgeJobResult `
                -BaseUrl $orchestratorUrl `
                -BridgeId $bridgeId `
                -BridgeToken $bridgeToken `
                -JobId $jobId `
                -Status 'ok' `
                -Result $result `
                -ErrorMessage $null | Out-Null

            Write-BridgeLog "Job $jobId завершён OK tool=$tool"
        }
        catch {
            Submit-BridgeJobResult `
                -BaseUrl $orchestratorUrl `
                -BridgeId $bridgeId `
                -BridgeToken $bridgeToken `
                -JobId $jobId `
                -Status 'error' `
                -Result $null `
                -ErrorMessage $_.Exception.Message | Out-Null

            Write-BridgeLog "Job $jobId ошибка: $($_.Exception.Message)"
        }
    }
    catch {
        Write-BridgeLog "Цикл агента: $($_.Exception.Message)"
        Start-Sleep -Seconds $pollIntervalSec
    }
}
