#Requires -Version 5.1
Set-StrictMode -Version Latest

function Write-1CPlatformMessage {
    param([string]$Message)
    if ($env:ONEC_AGENT_QUIET -eq '1') {
        return
    }
    Write-Host $Message
}

function Write-1CPlatformWarning {
    param([string]$Message)
    if ($env:ONEC_AGENT_QUIET -eq '1') {
        return
    }
    Write-Warning $Message
}

function Get-1CInstalledLocationFromCfg {
    $startCfg = Join-Path $env:APPDATA '1C\1CEStart\1cestart.cfg'
    if (-not (Test-Path -LiteralPath $startCfg)) {
        return $null
    }

    foreach ($line in (Get-Content -LiteralPath $startCfg -Encoding Default)) {
        if ($line -match '^InstalledLocation=(.+)$') {
            return $Matches[1].Trim()
        }
    }

    return $null
}

function Resolve-1CPlatformBinFromExplicitPath {
    param([Parameter(Mandatory = $true)][string]$ExplicitPath)

    if (Test-Path -LiteralPath $ExplicitPath -PathType Leaf) {
        return (Split-Path -LiteralPath $ExplicitPath -Parent)
    }

    if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Container)) {
        return $null
    }

    $normalized = $ExplicitPath.TrimEnd('\')

    if (Test-Path -LiteralPath (Join-Path $normalized 'comcntr.dll')) {
        return $normalized
    }

    $binNested = Join-Path $normalized 'bin'
    if (Test-Path -LiteralPath (Join-Path $binNested 'comcntr.dll')) {
        return $binNested
    }

    return $null
}

function Get-1CPlatformVersionFolderFromBin {
    param([Parameter(Mandatory = $true)][string]$BinPath)

    return Split-Path (Split-Path $BinPath -Parent) -Leaf
}

function Get-1CComConnectorProgId {
    param([Parameter(Mandatory = $true)][string]$PlatformVersionFolder)

    if ($PlatformVersionFolder -match '^8\.5\.') {
        return 'V85.COMConnector'
    }

    return 'V83.COMConnector'
}

function Sort-1CPlatformBinCandidates {
    param(
        [string[]]$Bins,
        [string]$PreferMajorVersion = ''
    )

    $sorted = @($Bins | Sort-Object {
        $versionFolder = Get-1CPlatformVersionFolderFromBin -BinPath $_
        if ($versionFolder -match '^\d+\.\d+\.\d+\.\d+$') {
            [version]$versionFolder
        }
        else {
            [version]'0.0.0.0'
        }
    } -Descending)

    if (-not $PreferMajorVersion) {
        return $sorted
    }

    $preferred = @($sorted | Where-Object {
        $versionFolder = Get-1CPlatformVersionFolderFromBin -BinPath $_
        $versionFolder -match "^$([regex]::Escape($PreferMajorVersion))\."
    })

    $others = @($sorted | Where-Object { $_ -notin $preferred })
    return @($preferred + $others)
}

function Get-1CPlatformBinCandidates {
    param(
        [string]$ExplicitPath,
        [string]$PreferMajorVersion = ''
    )

    $bins = New-Object System.Collections.Generic.List[string]

    if ($ExplicitPath) {
        $resolved = Resolve-1CPlatformBinFromExplicitPath -ExplicitPath $ExplicitPath
        if ($resolved) {
            return @($resolved)
        }

        Write-1CPlatformWarning "Указанный -PlatformPath не найден: $ExplicitPath"
        Write-1CPlatformWarning 'Пробую автопоиск по 1cestart.cfg и стандартным каталогам...'
    }

    $roots = New-Object System.Collections.Generic.List[string]
    $installedRoot = Get-1CInstalledLocationFromCfg
    if ($installedRoot) { [void]$roots.Add($installedRoot) }
    [void]$roots.Add((Join-Path $env:LOCALAPPDATA 'Programs\1cv8_x64'))
    [void]$roots.Add('C:\Program Files\1cv8')
    [void]$roots.Add('C:\Program Files (x86)\1cv8')

    foreach ($root in ($roots | Select-Object -Unique)) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        $found = Find-1CPlatformBinPathsUnderRoot -Root $root
        foreach ($bin in $found) {
            if ($bins -notcontains $bin) {
                [void]$bins.Add($bin)
            }
        }
    }

    if ($bins.Count -eq 0) {
        $cfgHint = if ($installedRoot) { " InstalledLocation=$installedRoot" } else { '' }
        throw "Платформа 1С не найдена.$cfgHint"
    }

    return Sort-1CPlatformBinCandidates -Bins $bins.ToArray() -PreferMajorVersion $PreferMajorVersion
}

function Get-1CPlatformBinPath {
    param(
        [string]$ExplicitPath,
        [string]$PreferMajorVersion = ''
    )

    $candidates = Get-1CPlatformBinCandidates -ExplicitPath $ExplicitPath -PreferMajorVersion $PreferMajorVersion
    return $candidates[0]
}

function Get-1CPlatformConnectCandidates {
    param(
        [string]$ExplicitPath,
        [string]$PreferMajorVersion = ''
    )

    $result = New-Object System.Collections.Generic.List[object]
    foreach ($bin in (Get-1CPlatformBinCandidates -ExplicitPath $ExplicitPath -PreferMajorVersion $PreferMajorVersion)) {
        $versionFolder = Get-1CPlatformVersionFolderFromBin -BinPath $bin
        $majorVersion = ''
        if ($versionFolder -match '^(\d+\.\d+)\.') {
            $majorVersion = $Matches[1]
        }

        $result.Add([pscustomobject]@{
            BinPath = $bin
            Version = $versionFolder
            MajorVersion = $majorVersion
            ProgId = (Get-1CComConnectorProgId -PlatformVersionFolder $versionFolder)
        })
    }

    return $result.ToArray()
}

function Find-1CPlatformBinPathsUnderRoot {
    param([Parameter(Mandatory = $true)][string]$Root)

    if (-not (Test-Path -LiteralPath $Root)) {
        return @()
    }

    $result = New-Object System.Collections.Generic.List[string]

    $versionDirs = @()
    try {
        $versionDirs = @(Get-ChildItem -LiteralPath $Root -Directory -ErrorAction Stop |
            Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' })
    }
    catch {
        return @()
    }

    foreach ($dir in $versionDirs) {
        $bin = Join-Path $dir.FullName 'bin'
        if (Test-Path -LiteralPath (Join-Path $bin 'comcntr.dll')) {
            [void]$result.Add($bin)
        }
    }

    if ($result.Count -gt 0) {
        return $result.ToArray()
    }

    try {
        $dlls = @(Get-ChildItem -LiteralPath $Root -Recurse -Filter 'comcntr.dll' -ErrorAction Stop)
        foreach ($dll in $dlls) {
            [void]$result.Add($dll.Directory.FullName)
        }
    }
    catch {
        return @()
    }

    return $result.ToArray()
}

function Find-1CPlatformBinUnderRoot {
    param([Parameter(Mandatory = $true)][string]$Root)

    $paths = Find-1CPlatformBinPathsUnderRoot -Root $Root
    if ($paths.Count -gt 0) {
        return (Sort-1CPlatformBinCandidates -Bins $paths)[0]
    }

    return $null
}

function Get-Regsvr32ExitMessage {
    param([int]$ExitCode)

    switch ($ExitCode) {
        5 { return 'Отказано в доступе. Подтвердите UAC или запустите Register-1CCom.cmd от имени администратора.' }
        3 { return 'Путь к comcntr.dll не найден.' }
        4 { return 'Не удалось загрузить comcntr.dll (несовместимая версия или повреждён файл).' }
        default { return "Неизвестная ошибка regsvr32 (код $ExitCode)." }
    }
}

function Test-1CComConnectorRegistered {
    param([string]$ProgId = 'V83.COMConnector')

    return $null -ne [Type]::GetTypeFromProgID($ProgId)
}

function Register-1CComConnector {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PlatformBinPath,
        [string]$ProgId = '',
        [switch]$Elevate,
        [switch]$Silent
    )

    if (-not $ProgId) {
        $versionFolder = Get-1CPlatformVersionFolderFromBin -BinPath $PlatformBinPath
        $ProgId = Get-1CComConnectorProgId -PlatformVersionFolder $versionFolder
    }

    if (Test-1CComConnectorRegistered -ProgId $ProgId) {
        return
    }

    $dll = Join-Path $PlatformBinPath 'comcntr.dll'
    if (-not (Test-Path -LiteralPath $dll)) {
        throw "Не найден comcntr.dll: $dll"
    }

    $regsvr32 = Join-Path $env:SystemRoot 'System32\regsvr32.exe'
    if (-not (Test-Path -LiteralPath $regsvr32)) {
        throw "regsvr32.exe not found: $regsvr32"
    }

    $useSilent = $Silent.IsPresent -or $env:ONEC_AGENT_QUIET -eq '1'
    $regsvrArgs = if ($useSilent) { @('/s', "`"$dll`"") } else { @("`"$dll`"") }

    Write-1CPlatformMessage "Registering ${ProgId}: $dll"
    if ($useSilent) {
        Write-1CPlatformMessage 'Confirm UAC prompt if shown (Do not click Cancel).'
    }
    else {
        Write-1CPlatformMessage 'Confirm UAC prompt. After registration expect: DllRegisterServer ... succeeded.'
    }

    if ($Elevate) {
        $proc = Start-Process -FilePath $regsvr32 -ArgumentList $regsvrArgs -Verb RunAs -Wait -PassThru
    }
    else {
        $proc = Start-Process -FilePath $regsvr32 -ArgumentList $regsvrArgs -Wait -PassThru -NoNewWindow
    }

    if ($proc.ExitCode -ne 0) {
        throw "$(Get-Regsvr32ExitMessage -ExitCode $proc.ExitCode) DLL: $dll"
    }

    if (-not (Test-1CComConnectorRegistered -ProgId $ProgId)) {
        throw "COM-коннектор $ProgId не зарегистрирован после regsvr32. Запустите Register-1CCom.cmd от имени администратора."
    }
}

function Show-1CComRegistrationStatus {
    param([string]$Title = 'COM status')

    Write-1CPlatformMessage ""
    Write-1CPlatformMessage "==> $Title"
    foreach ($progId in @('V83.COMConnector', 'V85.COMConnector')) {
        $ok = Test-1CComConnectorRegistered -ProgId $progId
        $label = if ($ok) { 'registered' } else { 'NOT registered' }
        Write-1CPlatformMessage "   $progId : $label"
    }

    try {
        foreach ($candidate in (Get-1CPlatformConnectCandidates)) {
            $dll = Join-Path $candidate.BinPath 'comcntr.dll'
            $exists = Test-Path -LiteralPath $dll
            Write-1CPlatformMessage "   $($candidate.Version) -> $dll (exists: $exists)"
        }
    }
    catch {
        Write-1CPlatformWarning "   Platform search: $($_.Exception.Message)"
    }
}

function Register-1CComConnectors {
    param(
        [string]$PlatformPath,
        [switch]$Elevate,
        [switch]$Silent
    )

    Show-1CComRegistrationStatus -Title 'Before registration'

    $registered = New-Object System.Collections.Generic.List[string]
    $seenProgIds = @{}

    foreach ($candidate in (Get-1CPlatformConnectCandidates -ExplicitPath $PlatformPath)) {
        if ($seenProgIds.ContainsKey($candidate.ProgId)) {
            continue
        }

        $seenProgIds[$candidate.ProgId] = $true

        if (Test-1CComConnectorRegistered -ProgId $candidate.ProgId) {
            Write-1CPlatformMessage "OK: $($candidate.ProgId) already registered ($($candidate.Version))."
            [void]$registered.Add($candidate.ProgId)
            continue
        }

        Register-1CComConnector -PlatformBinPath $candidate.BinPath -ProgId $candidate.ProgId -Elevate:$Elevate -Silent:$Silent
        [void]$registered.Add($candidate.ProgId)
    }

    if ($registered.Count -eq 0) {
        throw 'Не удалось зарегистрировать COM-коннекторы 1С.'
    }

    Show-1CComRegistrationStatus -Title 'After registration'
}

function Connect-1CInfobaseAuto {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConnectionString,
        [string]$PlatformPath = '',
        [string]$PreferMajorVersion = '',
        [string]$InfoBasePath = '',
        [string]$InfoBaseName = '',
        [switch]$RegisterCom
    )

    $resolvedPrefer = Normalize-1CPlatformMajorVersion -Version $PreferMajorVersion
    if (Get-Command Resolve-1CInfobasePreferPlatformVersion -ErrorAction SilentlyContinue) {
        $resolvedPrefer = Resolve-1CInfobasePreferPlatformVersion `
            -ConnectionString $ConnectionString `
            -InfoBasePath $InfoBasePath `
            -InfoBaseName $InfoBaseName `
            -PreferMajorVersion $PreferMajorVersion
    }

    $explicitPrefer = [bool]$PreferMajorVersion
    $candidates = Get-1CPlatformConnectCandidates -ExplicitPath $PlatformPath -PreferMajorVersion $resolvedPrefer
    if ($resolvedPrefer) {
        $filtered = @($candidates | Where-Object { $_.MajorVersion -eq $resolvedPrefer })
        if ($filtered.Count -eq 0) {
            $binsHint = ($candidates | ForEach-Object { $_.Version }) -join ', '
            $message = "Platform $resolvedPrefer not found (installed: $binsHint). Use major 8.3/8.5 only, not full version."
            throw $message
        }
        if ($explicitPrefer) {
            $candidates = $filtered
        }
        else {
            $others = @($candidates | Where-Object { $_.MajorVersion -ne $resolvedPrefer })
            $candidates = @($filtered + $others)
        }
    }
    elseif (-not $resolvedPrefer) {
        $registered = @($candidates | Where-Object { Test-1CComConnectorRegistered -ProgId $_.ProgId })
        if ($registered.Count -gt 0) {
            $candidates = $registered
        }
    }

    if ($candidates.Count -eq 0) {
        throw 'Не найдена установленная платформа 1С. Проверьте 1cestart.cfg (InstalledLocation) и Register-1CCom.cmd.'
    }

    $errors = New-Object System.Collections.Generic.List[string]

    $tryConnect = {
        param($CandidateList)

        foreach ($candidate in $CandidateList) {
            try {
                if ($RegisterCom -or -not (Test-1CComConnectorRegistered -ProgId $candidate.ProgId)) {
                    Register-1CComConnector -PlatformBinPath $candidate.BinPath -ProgId $candidate.ProgId -Elevate:$RegisterCom
                }

                if (-not (Test-1CComConnectorRegistered -ProgId $candidate.ProgId)) {
                    [void]$errors.Add("$($candidate.ProgId) ($($candidate.Version)): COM не зарегистрирован. Запустите Register-1CCom.cmd.")
                    continue
                }

                $connector = New-Object -ComObject $candidate.ProgId
                $connection = $connector.Connect($ConnectionString)

                $detectedFrom = 'auto'
                if ($resolvedPrefer) {
                    $detectedFrom = 'infobase_or_registry'
                }

                $ceStartPath = ''
                if (Get-Command Get-1CEStartExecutablePath -ErrorAction SilentlyContinue) {
                    $ceStartPath = [string](Get-1CEStartExecutablePath)
                }

                return [pscustomobject]@{
                    Connection = $connection
                    PlatformBin = $candidate.BinPath
                    PlatformVersion = $candidate.Version
                    PlatformMajor = $candidate.MajorVersion
                    ProgId = $candidate.ProgId
                    PreferMajorVersion = $resolvedPrefer
                    PlatformDetectedFrom = $detectedFrom
                    CEStartPath = $ceStartPath
                    InstalledLocation = $(if (Get-Command Get-1CEStartInstalledLocation -ErrorAction SilentlyContinue) {
                        Get-1CEStartInstalledLocation
                    } else { '' })
                }
            }
            catch {
                $message = $_.Exception.Message
                [void]$errors.Add("$($candidate.ProgId) ($($candidate.Version)): $message")
            }
        }

        return $null
    }

    $result = & $tryConnect $candidates
    if ($null -ne $result) {
        return $result
    }

    $requiredMajor = ''
    foreach ($err in $errors) {
        if ($err -match '(8\.5\.\d+\.\d+)') {
            $requiredMajor = '8.5'
            break
        }
        if ($err -match '(8\.3\.\d+\.\d+)') {
            $requiredMajor = '8.3'
            break
        }
    }

    if ($requiredMajor -and $requiredMajor -ne $resolvedPrefer) {
        $retryCandidates = Get-1CPlatformConnectCandidates -ExplicitPath $PlatformPath -PreferMajorVersion $requiredMajor
        $retryFiltered = @($retryCandidates | Where-Object { $_.MajorVersion -eq $requiredMajor })
        if ($retryFiltered.Count -gt 0) {
            $errors.Clear()
            $resolvedPrefer = $requiredMajor
            $result = & $tryConnect $retryFiltered
            if ($null -ne $result) {
                $result.PreferMajorVersion = $requiredMajor
                $result.PlatformDetectedFrom = 'version_mismatch_retry'
                return $result
            }
        }
    }

    $details = ($errors.ToArray() -join [Environment]::NewLine)
    $hint = "Подсказка: проверьте имя пользователя, пароль и право внешнего (COM) подключения. platform_version не передавать."
    if (-not (Test-1CComConnectorRegistered -ProgId 'V83.COMConnector') -and -not (Test-1CComConnectorRegistered -ProgId 'V85.COMConnector')) {
        $hint += " COM не зарегистрирован — Register-1CCom.cmd."
    }
    throw "Не удалось подключиться к базе ни через одну установленную платформу 1С:`n$details`n$hint"
}
