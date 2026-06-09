#Requires -Version 5.1
Set-StrictMode -Version Latest

$script:BridgeProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $script:BridgeProjectRoot 'Lib\1CInfoBase.ps1')
. (Join-Path $script:BridgeProjectRoot 'Lib\1CInfobaseVersion.ps1')
. (Join-Path $script:BridgeProjectRoot 'Lib\1CPlatform.ps1')

$script:BridgeConnection = $null
$script:BridgeConnector = $null
$script:BridgeConnectInfo = $null

function Test-BridgeQueryReadOnly {
    param([Parameter(Mandatory = $true)][string]$QueryText)

    $normalized = (($QueryText -replace '//.*', '') -replace '\s+', ' ').Trim()
    return [bool]($normalized -match '(?i)^(ВЫБРАТЬ|SELECT)\b')
}

function Convert-BridgeComValue {
    param($Connection, $Value)

    if ($null -eq $Value) {
        return $null
    }

    try {
        $stringValue = $Connection.String($Value)
        if ($stringValue -eq 'NULL' -or $stringValue -eq 'Неопределено') {
            return $null
        }
        return $stringValue
    }
    catch {
        return [string]$Value
    }
}

function Get-BridgeQueryColumnNames {
    param([Parameter(Mandatory = $true)][string]$QueryText)

    $normalized = ($QueryText -replace '//.*', '') -replace '\s+', ' '
    if ($normalized -notmatch '(?i)ВЫБРАТЬ\s+(.*?)\s+ИЗ\s') {
        if ($normalized -match '(?i)ВЫБРАТЬ\s+(.+)$') {
            $selectPart = $Matches[1].Trim()
        }
        else {
            return @()
        }
    }
    else {
        $selectPart = $Matches[1].Trim()
    }

    if (-not $selectPart) {
        return @()
    }
    if ($selectPart -match '(?i)^ПЕРВЫЕ\s+\d+\s+') {
        $selectPart = ($selectPart -replace '(?i)^ПЕРВЫЕ\s+\d+\s+', '').Trim()
    }
    if ($selectPart -match '(?i)^РАЗЛИЧНЫЕ\s+') {
        $selectPart = ($selectPart -replace '(?i)^РАЗЛИЧНЫЕ\s+', '').Trim()
    }

    $parts = $selectPart -split ',(?=(?:[^"]*"[^"]*")*[^"]*$)'
    $columns = @()
    foreach ($part in $parts) {
        $fieldExpr = $part.Trim()
        if ($fieldExpr -match '(?i)\s+КАК\s+([A-Za-zА-Яа-яЁё0-9_]+)\s*$') {
            $columns += $Matches[1]
        }
        elseif ($fieldExpr -match '(?i)([A-Za-zА-Яа-яЁё0-9_]+)\s*$') {
            $columns += $Matches[1]
        }
        else {
            $columns += "Column$($columns.Count)"
        }
    }
    return $columns
}

function Get-BridgeSelectionColumnCount {
    param($Selection)

    $count = 0
    while ($true) {
        try {
            $null = $Selection.Get($count)
            $count++
        }
        catch {
            break
        }
    }
    return $count
}

function Invoke-BridgeComQuery {
    param(
        [Parameter(Mandatory = $true)]
        $Connection,
        [Parameter(Mandatory = $true)]
        [string]$QueryText,
        [int]$MaxRows = 500
    )

    if (-not (Test-BridgeQueryReadOnly -QueryText $QueryText)) {
        throw 'Разрешены только запросы ВЫБРАТЬ/SELECT.'
    }

    $query = $Connection.NewObject('Query')
    $query.Text = $QueryText

    $selection = $query.Execute().Choose()
    $columnNames = @(Get-BridgeQueryColumnNames -QueryText $QueryText)

    if ($columnNames.Count -eq 0) {
        if ($selection.Next()) {
            $colCount = Get-BridgeSelectionColumnCount -Selection $selection
            $columnNames = @(for ($i = 0; $i -lt $colCount; $i++) { "Column$i" })
            $selection = $query.Execute().Choose()
        }
    }

    $rows = New-Object System.Collections.Generic.List[object]
    $totalRows = 0

    while ($selection.Next()) {
        $totalRows++
        if ($MaxRows -gt 0 -and $totalRows -gt $MaxRows) {
            break
        }

        $rowObject = [ordered]@{}
        for ($c = 0; $c -lt $columnNames.Count; $c++) {
            $columnName = $columnNames[$c]
            $cellValue = $selection.Get($c)
            $rowObject[$columnName] = Convert-BridgeComValue -Connection $Connection -Value $cellValue
        }
        $rows.Add([PSCustomObject]$rowObject)
    }

    if (@($columnNames).Count -eq 0 -and $rows.Count -gt 0) {
        $columnNames = @($rows[0].PSObject.Properties.Name)
    }

    $rowArray = @()
    foreach ($row in $rows) {
        $dict = [ordered]@{}
        foreach ($prop in $row.PSObject.Properties) {
            $dict[$prop.Name] = $prop.Value
        }
        $rowArray += $dict
    }

    return @{
        rowCount = $rows.Count
        totalRows = $totalRows
        columns = @($columnNames)
        rows = $rowArray
    }
}

function Build-BridgeConnectionString {
    param(
        [string]$InfoBasePath,
        [string]$Server,
        [string]$Ref,
        [string]$User,
        [string]$Password
    )

    if ($InfoBasePath) {
        $connectionString = "File=`"$InfoBasePath`";Usr=`"$User`";"
        if ($Password) {
            $connectionString += "Pwd=`"$Password`";"
        }
        return $connectionString
    }

    if ($Server -and $Ref) {
        $connectionString = "Srvr=`"$Server`";Ref=`"$Ref`";Usr=`"$User`";"
        if ($Password) {
            $connectionString += "Pwd=`"$Password`";"
        }
        return $connectionString
    }

    throw 'Укажите info_base_path (файловая) или server+ref (серверная) в bridge-agent.json.'
}

function Connect-BridgeComSession {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$ConnectionConfig,
        [string]$PlatformPath = ''
    )

    Disconnect-BridgeComSession

    $connectionString = Build-BridgeConnectionString `
        -InfoBasePath $ConnectionConfig.info_base_path `
        -Server $ConnectionConfig.server `
        -Ref $ConnectionConfig.ref `
        -User ($(if ($null -ne $ConnectionConfig.user) { $ConnectionConfig.user } else { '' })) `
        -Password ($(if ($null -ne $ConnectionConfig.password) { $ConnectionConfig.password } else { '' }))

    $result = Connect-1CInfobaseAuto `
        -ConnectionString $connectionString `
        -PlatformPath $PlatformPath `
        -InfoBasePath $ConnectionConfig.info_base_path `
        -InfoBaseName $ConnectionConfig.info_base_name

    $script:BridgeConnection = $result.Connection
    $script:BridgeConnector = $null
    $script:BridgeConnectInfo = @{
        platformVersion = $result.PlatformVersion
        progId = $result.ProgId
        connectionString = $connectionString
    }

    return $script:BridgeConnectInfo
}

function Disconnect-BridgeComSession {
    if ($null -ne $script:BridgeConnection) {
        try {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($script:BridgeConnection)
        }
        catch {
            # ignore
        }
        $script:BridgeConnection = $null
    }

    if ($null -ne $script:BridgeConnector) {
        try {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($script:BridgeConnector)
        }
        catch {
            # ignore
        }
        $script:BridgeConnector = $null
    }
}

function Get-BridgeComConnection {
    if ($null -eq $script:BridgeConnection) {
        throw 'COM-соединение не установлено.'
    }
    return $script:BridgeConnection
}

function Test-BridgeComHeartbeat {
    param([int]$MaxRows = 1)

    $connection = Get-BridgeComConnection
    $null = Invoke-BridgeComQuery -Connection $connection -QueryText 'ВЫБРАТЬ 1 КАК N' -MaxRows $MaxRows
    return $true
}

function Invoke-BridgeComWithReconnect {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$ConnectionConfig,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action,
        [string]$PlatformPath = ''
    )

    try {
        if ($null -eq $script:BridgeConnection) {
            Connect-BridgeComSession -ConnectionConfig $ConnectionConfig -PlatformPath $PlatformPath | Out-Null
        }
        return & $Action (Get-BridgeComConnection)
    }
    catch {
        Write-Warning "COM-ошибка, переподключение: $($_.Exception.Message)"
        Start-Sleep -Seconds 2
        Connect-BridgeComSession -ConnectionConfig $ConnectionConfig -PlatformPath $PlatformPath | Out-Null
        return & $Action (Get-BridgeComConnection)
    }
}
