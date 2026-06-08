#Requires -Version 5.1
Set-StrictMode -Version Latest

function Get-1CEStartCfgPath {
    Join-Path $env:APPDATA '1C\1CEStart\1cestart.cfg'
}

function Get-1CEStartInstalledLocation {
    $cfgPath = Get-1CEStartCfgPath
    if (-not (Test-Path -LiteralPath $cfgPath)) {
        return $null
    }

    foreach ($line in (Get-Content -LiteralPath $cfgPath -Encoding Default)) {
        if ($line -match '^InstalledLocation=(.+)$') {
            return $Matches[1].Trim()
        }
    }

    return $null
}

function Get-1CEStartExecutablePath {
    $installedRoot = Get-1CEStartInstalledLocation
    $searchRoots = New-Object System.Collections.Generic.List[string]

    if ($installedRoot) {
        [void]$searchRoots.Add($installedRoot)
    }

    [void]$searchRoots.Add((Join-Path $env:LOCALAPPDATA 'Programs\1cv8_x64'))
    [void]$searchRoots.Add('C:\Program Files\1cv8')
    [void]$searchRoots.Add('C:\Program Files (x86)\1cv8')

    foreach ($root in ($searchRoots | Select-Object -Unique)) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) {
            continue
        }

        try {
            $exes = @(Get-ChildItem -LiteralPath $root -Recurse -Filter '1cestart.exe' -ErrorAction Stop |
                Select-Object -First 1)
            if ($exes.Count -gt 0) {
                return $exes[0].FullName
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Get-1CInfobasePlatformVersionFromFile {
    param([Parameter(Mandatory = $true)][string]$InfoBasePath)

    if (-not $InfoBasePath -or -not (Test-Path -LiteralPath $InfoBasePath)) {
        return ''
    }

    $candidates = @(
        (Join-Path $InfoBasePath '1Cv8.1cd'),
        (Join-Path $InfoBasePath '1Cv8.1CD'),
        (Join-Path $InfoBasePath '1Cv8tmp.1cd')
    )

    foreach ($filePath in $candidates) {
        if (-not (Test-Path -LiteralPath $filePath)) {
            continue
        }

        try {
            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            if ($bytes.Length -eq 0) {
                continue
            }

            $encodings = @(
                [System.Text.Encoding]::Unicode,
                [System.Text.Encoding]::UTF8,
                [System.Text.Encoding]::Default
            )

            foreach ($encoding in $encodings) {
                $text = $encoding.GetString($bytes)
                $found = @([regex]::Matches($text, '8\.\d+\.\d+\.\d+') |
                    ForEach-Object { $_.Value } |
                    Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } |
                    Sort-Object { [version]$_ } -Descending |
                    Select-Object -First 1)
                if ($found.Count -gt 0) {
                    return $found[0]
                }
            }
        }
        catch {
            continue
        }
    }

    return ''
}

function Get-1CInfobasePlatformMajorVersion {
    param(
        [string]$InfoBasePath = '',
        [string]$InfoBaseName = ''
    )

    if ($InfoBaseName) {
        $versionFromRegistry = Get-1CInfoBaseVersionFromRegistry -InfoBaseName $InfoBaseName
        if ($versionFromRegistry) {
            return (Get-1CPlatformMajorFromFullVersion -Version $versionFromRegistry)
        }
    }

    if ($InfoBasePath) {
        $full = Get-1CInfobasePlatformVersionFromFile -InfoBasePath $InfoBasePath
        if ($full) {
            return (Get-1CPlatformMajorFromFullVersion -Version $full)
        }
    }

    return ''
}

function Get-1CPlatformMajorFromFullVersion {
    param([Parameter(Mandatory = $true)][string]$Version)

    $normalized = $Version.Trim()
    if ($normalized -match '^8\.5(\.\d+)*$') {
        return '8.5'
    }

    if ($normalized -match '^8\.3(\.\d+)*$') {
        return '8.3'
    }

    return ''
}

function Normalize-1CPlatformMajorVersion {
    param([string]$Version)

    if ([string]::IsNullOrWhiteSpace($Version)) {
        return ''
    }

    $trimmed = $Version.Trim()
    if ($trimmed -match '^8\.(3|5)$') {
        return $trimmed
    }

    return Get-1CPlatformMajorFromFullVersion -Version $trimmed
}

function Get-1CInfobasePathFromConnectionString {
    param([Parameter(Mandatory = $true)][string]$ConnectionString)

    if ($ConnectionString -match 'File="([^"]+)"') {
        return $Matches[1]
    }

    return ''
}

function Resolve-1CInfobasePreferPlatformVersion {
    param(
        [string]$ConnectionString = '',
        [string]$InfoBasePath = '',
        [string]$InfoBaseName = '',
        [string]$PreferMajorVersion = ''
    )

    if ($PreferMajorVersion) {
        $major = Normalize-1CPlatformMajorVersion -Version $PreferMajorVersion
        if ($major) {
            return $major
        }
        return $PreferMajorVersion.Trim()
    }

    if (-not $InfoBasePath) {
        $InfoBasePath = Get-1CInfobasePathFromConnectionString -ConnectionString $ConnectionString
    }

    $detected = Get-1CInfobasePlatformMajorVersion -InfoBasePath $InfoBasePath -InfoBaseName $InfoBaseName
    if ($detected) {
        return $detected
    }

    return ''
}
