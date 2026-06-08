#Requires -Version 5.1
<#
.SYNOPSIS
    Универсальное получение данных из информационной базы 1С через COM-коннектор.

.DESCRIPTION
    Скрипт подключается к файловой или серверной базе 1С, выполняет произвольный
    запрос на языке запросов 1С и возвращает результат в JSON или CSV.
    Предназначен для автоматизации анализа данных (в т.ч. с помощью ИИ).

.PARAMETER InfoBasePath
    Путь к каталогу файловой информационной базы.

.PARAMETER Server
    Имя сервера 1С (для серверной базы).

.PARAMETER Ref
    Имя информационной базы на сервере.

.PARAMETER User
    Имя пользователя 1С. По умолчанию — пустой пользователь.

.PARAMETER Password
    Пароль пользователя 1С.

.PARAMETER ConnectionString
    Готовая строка подключения 1С (перекрывает InfoBasePath/Server/Ref).

.PARAMETER InfoBaseName
    Имя базы из ibases.v8i (реестр баз пользователя).

.PARAMETER Query
    Текст запроса на языке запросов 1С.

.PARAMETER QueryFile
    Путь к файлу с текстом запроса (UTF-8).

.PARAMETER OutputFormat
    Формат вывода: Json (по умолчанию), Csv, Table.

.PARAMETER OutputFile
    Путь для сохранения результата. Без параметра — stdout.

.PARAMETER MaxRows
    Ограничение количества строк результата (0 = без ограничения). В режиме -AgentMode по умолчанию 500.

.PARAMETER ReadOnly
    Разрешить только запросы ВЫБРАТЬ/SELECT. Включается автоматически с -AgentMode.

.PARAMETER AgentMode
    Режим для ИИ/MCP: ReadOnly, MaxRows=500 (если не задан), чистый JSON в stdout.

.PARAMETER Quiet
    Не выводить служебные сообщения в stdout (только результат).

.PARAMETER PlatformPath
    Каталог bin платформы 1С или путь к 1cv8.exe.

.PARAMETER RegisterCom
    Зарегистрировать comcntr.dll перед подключением (может потребовать UAC).

.PARAMETER ListInfoBases
    Вывести список баз из ibases.v8i и завершить работу.

.PARAMETER ExportMetadata
    Выгрузить метаданные конфигурации из подключённой ИБ в metadata/cache (JSON).

.PARAMETER ForceMetadataRefresh
    Пересоздать кэш метаданных даже если он свежий.

.EXAMPLE
    .\Get-1CData.ps1 -InfoBasePath "C:\Users\aaposmetev\Documents\1C\DemoTrd" -Query "ВЫБРАТЬ ПЕРВЫЕ 10 Наименование, ИНН ИЗ Справочник.Контрагенты"

.EXAMPLE
    .\Get-1CData.ps1 -InfoBaseName "Управление торговлей (демо)" -QueryFile .\queries\counterparties.txt

.EXAMPLE
    .\Get-1CData.ps1 -RegisterCom -InfoBasePath "C:\ib\base" -Query "ВЫБРАТЬ 1 КАК N"
#>
[CmdletBinding(DefaultParameterSetName = 'Query')]
param(
    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$InfoBasePath,

    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$Server,

    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$Ref,

    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$User = "",

    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$Password = "",

    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$ConnectionString,

    [Parameter(ParameterSetName = 'Query')]
    [Parameter(ParameterSetName = 'QueryFile')]
    [Parameter(ParameterSetName = 'ExportMetadata')]
    [Parameter(ParameterSetName = 'ReadModule')]
    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$InfoBaseName,

    [Parameter(ParameterSetName = 'Query', Mandatory = $true)]
    [string]$Query,

    [Parameter(ParameterSetName = 'QueryFile', Mandatory = $true)]
    [string]$QueryFile,

    [Parameter(ParameterSetName = 'List', Mandatory = $true)]
    [switch]$ListInfoBases,

    [Parameter(ParameterSetName = 'ExportMetadata', Mandatory = $true)]
    [switch]$ExportMetadata,

    [Parameter(ParameterSetName = 'ExportMetadata')]
    [switch]$ForceMetadataRefresh,

    [Parameter(ParameterSetName = 'DumpConfig', Mandatory = $true)]
    [switch]$DumpConfig,

    [Parameter(ParameterSetName = 'ReadModule', Mandatory = $true)]
    [switch]$ReadModule,

    [Parameter(ParameterSetName = 'ReadModule', Mandatory = $true)]
    [string]$ModuleFullName,

    [Parameter(ParameterSetName = 'ReadModule')]
    [ValidateSet('manager', 'object', 'module')]
    [string]$ModulePart = 'manager',

    [Parameter(ParameterSetName = 'ReadModule')]
    [string]$TargetKey = '',

    [Parameter(ParameterSetName = 'ReadModule')]
    [int]$ModuleMaxLines = 400,

    [Parameter(ParameterSetName = 'ReadModule')]
    [switch]$ForceModuleRefresh,

    [Parameter(ParameterSetName = 'DumpConfig')]
    [ValidateSet('Full', 'Partial')]
    [string]$DumpMode = 'Partial',

    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$DumpObjects = '',

    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$DumpOutputPath = '',

    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$DumpTargetKey = '',

    [Parameter(ParameterSetName = 'DumpConfig')]
    [string]$DumpExtension = '',

    [ValidateSet('Json', 'Csv', 'Table')]
    [string]$OutputFormat = 'Json',

    [string]$OutputFile,

    [int]$MaxRows = -1,

    [switch]$ReadOnly,

    [switch]$AgentMode,

    [switch]$Quiet,

    [string]$PlatformPath,

    [string]$PreferPlatformVersion,

    [switch]$RegisterCom
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'Lib\1CInfoBase.ps1')
. (Join-Path $PSScriptRoot 'Lib\1CInfobaseVersion.ps1')
. (Join-Path $PSScriptRoot 'Lib\1CPlatform.ps1')
. (Join-Path $PSScriptRoot 'Lib\1CMetadataExport.ps1')
. (Join-Path $PSScriptRoot 'Lib\1CConfiguratorRead.ps1')
. (Join-Path $PSScriptRoot 'Lib\1CConfigDump.ps1')

function Get-1CConnectErrorKind {
    param([Parameter(Mandatory = $true)][string]$Message)

    $text = $Message.ToLowerInvariant()
    if ($text -match 'неверно указано имя пользователя|неверный пароль|неправильный пароль|incorrect password|authentication failed') {
        return 'auth'
    }
    if ($text -match 'внешнее соединение|внешнего соединения|не разрешено для указанного пользователя|external connection') {
        return 'external_denied'
    }
    if ($text -match 'parsererror|unexpected token|utf-8 bom') {
        return 'parser'
    }
    if ($text -match 'не найдена среди установленных|platform not found|платформа 1с не найдена') {
        return 'platform'
    }
    if ($text -match 'разрешено только|отверг запрос|connection refused|блокиров|уже начат') {
        return 'session_lock'
    }
    if ($text -match 'com не зарегистрирован|com-коннектор не зарегистрирован|не зарегистрирован после regsvr32|gettypefromprogid') {
        return 'com'
    }
    return 'connect'
}

function Write-1CError {
    param([string]$Message)
    if ($script:QuietMode) {
        $payload = [ordered]@{
            status    = 'error'
            message   = $Message
            errorKind = (Get-1CConnectErrorKind -Message $Message)
        }
        Write-Output ([PSCustomObject]$payload | ConvertTo-Json -Compress -Depth 4)
        exit 1
    }
    Write-Error $Message
}

function Write-1CInfo {
    param([string]$Message)
    if (-not $script:QuietMode) {
        Write-Host $Message
    }
}

function Test-1CQueryReadOnly {
    param([Parameter(Mandatory = $true)][string]$QueryText)

    $normalized = (($QueryText -replace '//.*', '') -replace '\s+', ' ').Trim()
    if ($normalized -match '(?i)^(ВЫБРАТЬ|SELECT)\b') {
        return $true
    }

    return $false
}

function Assert-1CQueryReadOnly {
    param([Parameter(Mandatory = $true)][string]$QueryText)

    if (-not (Test-1CQueryReadOnly -QueryText $QueryText)) {
        Write-1CError "ReadOnly: допустимы только запросы, начинающиеся с ВЫБРАТЬ или SELECT."
    }
}

function Build-1CConnectionString {
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

    Write-1CError "Укажите -InfoBasePath для файловой базы или пару -Server и -Ref для серверной."
}

function Connect-1CInfobase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConnectionString,
        [string]$PlatformPath = '',
        [string]$PreferMajorVersion = '',
        [string]$InfoBasePath = '',
        [string]$InfoBaseName = '',
        [switch]$RegisterCom
    )

    $result = Connect-1CInfobaseAuto -ConnectionString $ConnectionString `
        -PlatformPath $PlatformPath `
        -PreferMajorVersion $PreferMajorVersion `
        -InfoBasePath $InfoBasePath `
        -InfoBaseName $InfoBaseName `
        -RegisterCom:$RegisterCom

    $script:LastConnectResult = $result
    return $result.Connection
}

function Convert-1CComValue {
    param(
        $Connection,
        $Value
    )

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

function Get-1CQueryColumnNames {
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

function Get-1CSelectionColumnCount {
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

function Invoke-1CQuery {
    param(
        $Connection,
        [Parameter(Mandatory = $true)]
        [string]$QueryText,
        [int]$MaxRows = 0
    )

    $query = $Connection.NewObject('Query')
    $query.Text = $QueryText

    $selection = $query.Execute().Choose()
    $columnNames = @(Get-1CQueryColumnNames -QueryText $QueryText)

    if ($columnNames.Count -eq 0) {
        if ($selection.Next()) {
            $colCount = Get-1CSelectionColumnCount -Selection $selection
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
            $rowObject[$columnName] = Convert-1CComValue -Connection $Connection -Value $cellValue
        }

        $rows.Add([PSCustomObject]$rowObject)
    }

    if (@($columnNames).Count -eq 0 -and $rows.Count -gt 0) {
        $columnNames = @($rows[0].PSObject.Properties.Name)
    }

    return [PSCustomObject]@{
        RowCount = $rows.Count
        TotalRows = $totalRows
        Columns = $columnNames
        Rows = $rows.ToArray()
    }
}

function Write-1CQueryResult {
    param(
        $Result,
        [string]$Format,
        [string]$Path
    )

    switch ($Format) {
        'Json' {
            $payload = [ordered]@{
                rowCount = $Result.RowCount
                totalRows = $Result.TotalRows
                columns = $Result.Columns
                data = $Result.Rows
            }
            if ($null -ne $script:LastConnectResult) {
                $payload['platform'] = [ordered]@{
                    version = $script:LastConnectResult.PlatformVersion
                    major = $script:LastConnectResult.PlatformMajor
                    progId = $script:LastConnectResult.ProgId
                    preferMajor = $script:LastConnectResult.PreferMajorVersion
                    detectedFrom = $script:LastConnectResult.PlatformDetectedFrom
                    cestartPath = $script:LastConnectResult.CEStartPath
                    installedLocation = $script:LastConnectResult.InstalledLocation
                }
            }
            $useCompress = $script:QuietMode
            $text = ([PSCustomObject]$payload) | ConvertTo-Json -Depth 6 -Compress:$useCompress
        }
        'Csv' {
            $text = $Result.Rows | ConvertTo-Csv -NoTypeInformation
            $text = ($text -join [Environment]::NewLine)
        }
        'Table' {
            if ($Path) {
                Write-1CError "Формат Table поддерживается только для вывода в консоль."
            }
            $Result.Rows | Format-Table -AutoSize | Out-String -Width 4096 | Write-Output
            return
        }
    }

    if ($Path) {
        $text | Out-File -LiteralPath $Path -Encoding UTF8
        Write-1CInfo "Результат сохранён: $Path"
    }
    else {
        Write-Output $text
    }
}

function Write-1CInfoBaseListResult {
    param(
        $Bases,
        [string]$Format
    )

    if ($Format -eq 'Json') {
        $payload = @()
        foreach ($base in @($Bases)) {
            if ($null -eq $base) { continue }
            $payload += [PSCustomObject]@{
                name = Get-1CInfoBaseProperty -Item $base -Names @('Name', 'name')
                connect = Get-1CInfoBaseProperty -Item $base -Names @('Connect', 'connect')
            }
        }
        Write-Output ($payload | ConvertTo-Json -Depth 3 -Compress)
        return
    }

    if (-not $Bases) {
        Write-1CInfo "Реестр баз ibases.v8i не найден или пуст."
        return
    }

    $Bases | Format-Table Name, Connect -AutoSize | Out-String -Width 4096 | Write-Output
}

# --- main ---

$script:QuietMode = $Quiet -or $AgentMode

if ($AgentMode) {
    $ReadOnly = $true
    $env:ONEC_AGENT_QUIET = '1'
    $WarningPreference = 'SilentlyContinue'
    if ($MaxRows -lt 0) {
        $MaxRows = 500
    }
}
elseif ($MaxRows -lt 0) {
    $MaxRows = 0
}

if ($ListInfoBases) {
    $bases = Get-1CInfoBaseList
    $listFormat = if ($OutputFormat -eq 'Json') { 'Json' } else { 'Table' }
    Write-1CInfoBaseListResult -Bases $bases -Format $listFormat
    exit 0
}

if ($ExportMetadata -or $ReadModule -or $DumpConfig) {
    $AgentMode = $true
}

if ($PSCmdlet.ParameterSetName -eq 'QueryFile') {
    if (-not (Test-Path -LiteralPath $QueryFile)) {
        Write-1CError "Файл запроса не найден: $QueryFile"
    }
    $Query = Get-Content -LiteralPath $QueryFile -Raw -Encoding UTF8
}

if ($InfoBaseName) {
    $bases = Get-1CInfoBaseList
    $match = $bases | Where-Object { $_.Name -eq $InfoBaseName } | Select-Object -First 1
    if (-not $match) {
        $available = ($bases | ForEach-Object { $_.Name }) -join '; '
        Write-1CError "База '$InfoBaseName' не найдена в ibases.v8i. Доступные: $available"
    }
    $parsed = ConvertFrom-1CConnectString -Connect $match.Connect
    if (-not $InfoBasePath) { $InfoBasePath = $parsed.InfoBasePath }
    if (-not $Server) { $Server = $parsed.Server }
    if (-not $Ref) { $Ref = $parsed.Ref }
}

if (-not $ConnectionString) {
    $ConnectionString = Build-1CConnectionString -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref -User $User -Password $Password
}

if ($DumpConfig) {
    if (-not $DumpTargetKey) {
        if ($InfoBasePath) {
            $DumpTargetKey = "file:$InfoBasePath"
        }
        elseif ($Server -and $Ref) {
            $DumpTargetKey = "server:$Server/$Ref"
        }
        else {
            $DumpTargetKey = 'unknown'
        }
    }

    $objectList = @()
    if ($DumpObjects) {
        $objectList = @($DumpObjects -split '[,;\r\n]+' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }

    try {
        $result = Export-1CConfigToFiles -ProjectRoot $PSScriptRoot -TargetKey $DumpTargetKey `
            -Mode $DumpMode -Objects $objectList `
            -OutputPath $DumpOutputPath `
            -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref `
            -User $User -Password $Password `
            -PlatformPath $PlatformPath -PreferMajorVersion $PreferPlatformVersion `
            -Extension $DumpExtension
        Write-1CConfigDumpResult -Result $result
    }
    catch {
        Write-1CError $_.Exception.Message
    }
    exit 0
}

if ($ReadModule) {
    if (-not $TargetKey) {
        if ($InfoBasePath) {
            $TargetKey = "file:$InfoBasePath"
        }
        elseif ($Server -and $Ref) {
            $TargetKey = "server:$Server/$Ref"
        }
        else {
            $TargetKey = 'unknown'
        }
    }

    $result = Read-1CModuleFromInfobase -ProjectRoot $PSScriptRoot -TargetKey $TargetKey `
        -FullName $ModuleFullName -ModulePart $ModulePart `
        -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref `
        -User $User -Password $Password `
        -PlatformPath $PlatformPath -PreferMajorVersion $PreferPlatformVersion `
        -MaxLines $ModuleMaxLines -ForceRefresh:$ForceModuleRefresh
    Write-1CModuleReadResult -Result $result
    exit 0
}

if (-not $PreferPlatformVersion) {
    $PreferPlatformVersion = $env:ONEC_PLATFORM_VERSION
}

if ($RegisterCom) {
    Register-1CComConnectors -PlatformPath $PlatformPath -Elevate
}
elseif (-not (Test-1CComConnectorRegistered -ProgId 'V85.COMConnector') -and -not (Test-1CComConnectorRegistered -ProgId 'V83.COMConnector')) {
    Write-1CInfo "COM-коннектор не зарегистрирован. Попытка регистрации comcntr.dll..."
    Register-1CComConnectors -PlatformPath $PlatformPath -Elevate
}

if ($ReadOnly -and -not $ExportMetadata -and -not $ReadModule) {
    Assert-1CQueryReadOnly -QueryText $Query
}

try {
    $connection = Connect-1CInfobase -ConnectionString $ConnectionString `
        -PlatformPath $PlatformPath `
        -PreferMajorVersion $PreferPlatformVersion `
        -InfoBasePath $InfoBasePath `
        -InfoBaseName $InfoBaseName `
        -RegisterCom:$RegisterCom
}
catch {
    Write-1CError $_.Exception.Message
}

if ($ExportMetadata) {
    try {
        $cacheRoot = Join-Path $PSScriptRoot 'metadata\cache'
        $exportResult = Export-1CMetadataToCache -Connection $connection `
            -CacheRoot $cacheRoot `
            -InfoBasePath $InfoBasePath `
            -Server $Server `
            -Ref $Ref `
            -Force:$ForceMetadataRefresh
        Write-1CMetadataExportResult -Result $exportResult -Format 'Json'
    }
    finally {
        if ($null -ne $connection) {
            [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($connection)
        }
    }
    exit 0
}

try {
    $result = Invoke-1CQuery -Connection $connection -QueryText $Query -MaxRows $MaxRows
    Write-1CQueryResult -Result $result -Format $OutputFormat -Path $OutputFile
}
finally {
    if ($null -ne $connection) {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($connection)
    }
}
