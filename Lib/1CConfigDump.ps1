#Requires -Version 5.1
Set-StrictMode -Version Latest

function Get-1CConfigDumpRoot {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$TargetKey
    )

    $safe = ($TargetKey -replace '[^\w\-.]+', '_').Trim('_')
    if (-not $safe) { $safe = 'unknown' }
    return Join-Path $ProjectRoot ("metadata\config-sources\{0}" -f $safe)
}

function Invoke-1CDesignerDumpConfigToFiles {
    param(
        [Parameter(Mandatory = $true)][string]$V8Exe,
        [string]$InfoBasePath = '',
        [string]$Server = '',
        [string]$Ref = '',
        [string]$User = '',
        [string]$Password = '',
        [Parameter(Mandatory = $true)][string]$OutDir,
        [ValidateSet('Full', 'Partial')]
        [string]$Mode = 'Partial',
        [string[]]$Objects = @(),
        [string]$Extension = '',
        [ValidateSet('Hierarchical', 'Plain')]
        [string]$Format = 'Hierarchical'
    )

    if ($Mode -eq 'Partial' -and $Objects.Count -eq 0) {
        throw 'Для Partial укажите хотя бы один объект метаданных (например Документ.ЗаказКлиента).'
    }

    if (-not (Test-Path -LiteralPath $OutDir)) {
        New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
    }

    $tempDir = Join-Path $env:TEMP ("onec_config_dump_{0}" -f [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    try {
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
            throw 'Не задан путь к базе или server/ref.'
        }

        if ($User) { $arguments += "/N`"$User`"" }
        if ($Password) { $arguments += "/P`"$Password`"" }

        $arguments += '/DumpConfigToFiles', "`"$OutDir`"", '-Format', $Format

        if ($Mode -eq 'Partial') {
            $listFile = Join-Path $tempDir 'objects.txt'
            $utf8Bom = New-Object System.Text.UTF8Encoding($true)
            [System.IO.File]::WriteAllLines($listFile, $Objects, $utf8Bom)
            $arguments += '-listFile', "`"$listFile`""
        }

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

        $bslCount = @(Get-ChildItem -LiteralPath $OutDir -Recurse -Filter '*.bsl' -ErrorAction SilentlyContinue).Count
        $xmlCount = @(Get-ChildItem -LiteralPath $OutDir -Recurse -Filter '*.xml' -ErrorAction SilentlyContinue).Count

        return @{
            status = 'ok'
            mode = $Mode
            outDir = $OutDir
            objects = @($Objects)
            bslCount = $bslCount
            xmlCount = $xmlCount
            log = $logText
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

function Export-1CConfigToFiles {
    param(
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [Parameter(Mandatory = $true)][string]$TargetKey,
        [ValidateSet('Full', 'Partial')]
        [string]$Mode = 'Partial',
        [string[]]$Objects = @(),
        [string]$OutputPath = '',
        [string]$InfoBasePath = '',
        [string]$Server = '',
        [string]$Ref = '',
        [string]$User = '',
        [string]$Password = '',
        [string]$PlatformPath = '',
        [string]$PreferMajorVersion = '',
        [string]$Extension = ''
    )

    $outDir = $OutputPath
    if (-not $outDir) {
        $outDir = Get-1CConfigDumpRoot -ProjectRoot $ProjectRoot -TargetKey $TargetKey
    }

    $v8 = Get-1Cv8ExecutablePath -PlatformPath $PlatformPath -PreferMajorVersion $PreferMajorVersion
    $result = Invoke-1CDesignerDumpConfigToFiles -V8Exe $v8 `
        -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref `
        -User $User -Password $Password `
        -OutDir $outDir -Mode $Mode -Objects $Objects -Extension $Extension

    $result.targetKey = $TargetKey
    return $result
}

function Write-1CConfigDumpResult {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Result
    )

    $Result | ConvertTo-Json -Depth 5 | Write-Output
}

function Test-1CConfigSourcesPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $configXml = Join-Path $Path 'Configuration.xml'
    if (Test-Path -LiteralPath $configXml) {
        return $true
    }

    $markers = @('Catalogs', 'Documents', 'CommonModules', 'DataProcessors', 'Reports')
    foreach ($name in $markers) {
        $dir = Join-Path $Path $name
        if (Test-Path -LiteralPath $dir) {
            return $true
        }
    }

    return $false
}

function Get-1CConfigSourcesStats {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    $bsl = @(Get-ChildItem -LiteralPath $Path -Recurse -Filter '*.bsl' -ErrorAction SilentlyContinue)
    $xml = @(Get-ChildItem -LiteralPath $Path -Recurse -Filter '*.xml' -ErrorAction SilentlyContinue)
    return @{
        bslCount = $bsl.Count
        xmlCount = $xml.Count
        hasConfigurationXml = Test-Path -LiteralPath (Join-Path $Path 'Configuration.xml')
    }
}
