#Requires -Version 5.1
Set-StrictMode -Version Latest

function Get-1Cv8ExecutablePath {
    param(
        [string]$PlatformPath = '',
        [string]$PreferMajorVersion = ''
    )

    $candidates = Get-1CPlatformConnectCandidates -ExplicitPath $PlatformPath -PreferMajorVersion $PreferMajorVersion
    if ($candidates.Count -eq 0) {
        throw 'Не найдена установленная платформа 1С (1cv8.exe).'
    }

    $binPath = $candidates[0].BinPath
    $exe = Join-Path $binPath '1cv8.exe'
    if (-not (Test-Path -LiteralPath $exe)) {
        throw "Файл не найден: $exe"
    }

    return $exe
}

function Get-1CMetadataFolderMap {
    return @{
        'Справочник' = 'Catalogs'
        'Документ' = 'Documents'
        'ОбщийМодуль' = 'CommonModules'
        'РегистрСведений' = 'InformationRegisters'
        'РегистрНакопления' = 'AccumulationRegisters'
        'Обработка' = 'DataProcessors'
        'Отчет' = 'Reports'
        'Перечисление' = 'Enums'
        'Константа' = 'Constants'
        'ПланВидовХарактеристик' = 'ChartsOfCharacteristicTypes'
        'ПланСчетов' = 'ChartsOfAccounts'
        'ПланОбмена' = 'ExchangePlans'
        'БизнесПроцесс' = 'BusinessProcesses'
        'Задача' = 'Tasks'
    }
}

function ConvertFrom-1CMetadataFullName {
    param([Parameter(Mandatory = $true)][string]$FullName)

    $trimmed = $FullName.Trim()
    if ($trimmed -notmatch '^([^.]+)\.(.+)$') {
        throw "Некорректное полное имя объекта: $FullName. Ожидается, например, Документ.ЗаказКлиента."
    }

    return @{
        TypePrefix = $Matches[1]
        ObjectName = $Matches[2]
    }
}

function Get-1CModuleRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$FullName,
        [ValidateSet('manager', 'object', 'module')]
        [string]$ModulePart = 'manager'
    )

    $parsed = ConvertFrom-1CMetadataFullName -FullName $FullName
    $map = Get-1CMetadataFolderMap
    $folder = $map[$parsed.TypePrefix]
    if (-not $folder) {
        throw "Тип метаданных не поддерживается для чтения модуля: $($parsed.TypePrefix)"
    }

    $fileName = switch ($ModulePart) {
        'manager' { 'ManagerModule.bsl' }
        'object' { 'ObjectModule.bsl' }
        'module' { 'Module.bsl' }
    }

    if ($parsed.TypePrefix -eq 'ОбщийМодуль') {
        $fileName = 'Module.bsl'
    }

    $objectDir = Join-Path (Join-Path $folder $parsed.ObjectName) 'Ext'
    return Join-Path $objectDir $fileName
}

function Invoke-1CDesignerPartialDump {
    param(
        [Parameter(Mandatory = $true)][string]$V8Exe,
        [string]$InfoBasePath = '',
        [string]$Server = '',
        [string]$Ref = '',
        [string]$User = '',
        [string]$Password = '',
        [Parameter(Mandatory = $true)][string[]]$Objects,
        [Parameter(Mandatory = $true)][string]$OutDir,
        [string]$Extension = ''
    )

    if (-not (Test-Path -LiteralPath $OutDir)) {
        New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
    }

    $tempDir = Join-Path $env:TEMP ("onec_partial_dump_{0}" -f [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    try {
        $listFile = Join-Path $tempDir 'objects.txt'
        $utf8Bom = New-Object System.Text.UTF8Encoding($true)
        [System.IO.File]::WriteAllLines($listFile, $Objects, $utf8Bom)

        $arguments = @(
            'DESIGNER',
            '/DisableStartupDialogs'
        )

        if ($Server -and $Ref) {
            $arguments += '/S', "`"$Server/$Ref`""
        }
        elseif ($InfoBasePath) {
            $arguments += '/F', "`"$InfoBasePath`""
        }
        else {
            throw 'Не задан путь к базе или сервер/ref.'
        }

        if ($User) { $arguments += "/N`"$User`"" }
        if ($Password) { $arguments += "/P`"$Password`"" }

        $arguments += '/DumpConfigToFiles', "`"$OutDir`"", '-Format', 'Hierarchical', '-listFile', "`"$listFile`""

        if ($Extension) {
            $arguments += '-Extension', "`"$Extension`""
        }

        $outFile = Join-Path $tempDir 'designer.log'
        $arguments += '/Out', "`"$outFile`""

        $process = Start-Process -FilePath $V8Exe -ArgumentList $arguments -NoNewWindow -Wait -PassThru
        $logText = ''
        if (Test-Path -LiteralPath $outFile) {
            $logText = Get-Content -LiteralPath $outFile -Raw -Encoding UTF8
        }

        if ($process.ExitCode -ne 0) {
            throw "Конфигуратор завершился с кодом $($process.ExitCode). Лог: $logText"
        }

        return @{
            ExitCode = 0
            Log = $logText
            OutDir = $OutDir
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-1CModuleCacheRoot {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$TargetKey
    )

    $safe = ($TargetKey -replace '[^\w\-.]+', '_').Trim('_')
    if (-not $safe) { $safe = 'unknown' }
    return Join-Path $ProjectRoot ("metadata\module-cache\{0}" -f $safe)
}

function Read-1CModuleFromInfobase {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$TargetKey,
        [Parameter(Mandatory = $true)][string]$FullName,
        [ValidateSet('manager', 'object', 'module')]
        [string]$ModulePart = 'manager',
        [string]$InfoBasePath = '',
        [string]$Server = '',
        [string]$Ref = '',
        [string]$User = '',
        [string]$Password = '',
        [string]$PlatformPath = '',
        [string]$PreferMajorVersion = '',
        [int]$MaxLines = 400,
        [switch]$ForceRefresh
    )

    $relativePath = Get-1CModuleRelativePath -FullName $FullName -ModulePart $ModulePart
    $cacheRoot = Get-1CModuleCacheRoot -ProjectRoot $ProjectRoot -TargetKey $TargetKey
    $moduleFile = Join-Path $cacheRoot $relativePath

    if (-not $ForceRefresh -and (Test-Path -LiteralPath $moduleFile)) {
        return Get-1CModuleReadPayload -ModuleFile $moduleFile -FullName $FullName -ModulePart $ModulePart -MaxLines $MaxLines -FromCache $true
    }

    $v8 = Get-1Cv8ExecutablePath -PlatformPath $PlatformPath -PreferMajorVersion $PreferMajorVersion
    $null = Invoke-1CDesignerPartialDump -V8Exe $v8 `
        -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref `
        -User $User -Password $Password `
        -Objects @($FullName) `
        -OutDir $cacheRoot

    if (-not (Test-Path -LiteralPath $moduleFile)) {
        $found = Get-ChildItem -LiteralPath $cacheRoot -Recurse -Filter '*.bsl' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like "*$((ConvertFrom-1CMetadataFullName -FullName $FullName).ObjectName)*" }
        if ($found) {
            $moduleFile = $found[0].FullName
        }
        else {
            throw "Модуль не найден после выгрузки: $relativePath. Проверьте имя объекта и часть модуля ($ModulePart)."
        }
    }

    return Get-1CModuleReadPayload -ModuleFile $moduleFile -FullName $FullName -ModulePart $ModulePart -MaxLines $MaxLines -FromCache $false
}

function Get-1CModuleReadPayload {
    param(
        [Parameter(Mandatory = $true)][string]$ModuleFile,
        [Parameter(Mandatory = $true)][string]$FullName,
        [Parameter(Mandatory = $true)][string]$ModulePart,
        [int]$MaxLines = 400,
        [bool]$FromCache = $false
    )

    if ($MaxLines -lt 50) { $MaxLines = 50 }
    if ($MaxLines -gt 2000) { $MaxLines = 2000 }

    $lines = Get-Content -LiteralPath $ModuleFile -Encoding UTF8
    $total = $lines.Count
    $truncated = $total -gt $MaxLines
    $slice = if ($truncated) { $lines[0..($MaxLines - 1)] } else { $lines }

    return @{
        status = 'ok'
        fullName = $FullName
        modulePart = $ModulePart
        filePath = $ModuleFile
        lineCount = $total
        truncated = $truncated
        fromCache = $FromCache
        text = ($slice -join [Environment]::NewLine)
    }
}

function Write-1CModuleReadResult {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Result
    )

    $Result | ConvertTo-Json -Depth 4 | Write-Output
}

function Find-1CModulesUnderCache {
    param(
        [Parameter(Mandatory = $true)][string]$CacheRoot,
        [Parameter(Mandatory = $true)][string]$FullName
    )

    $parsed = ConvertFrom-1CMetadataFullName -FullName $FullName
    $pattern = "*$($parsed.ObjectName)*"
    $files = Get-ChildItem -LiteralPath $CacheRoot -Recurse -Filter '*.bsl' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like $pattern }

    return @($files | ForEach-Object {
        @{
            path = $_.FullName.Replace($CacheRoot, '').TrimStart('\')
            name = $_.Name
        }
    })
}
