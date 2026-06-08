#Requires -Version 5.1
Set-StrictMode -Version Latest

function Get-1CInfoBaseRegistryPath {
    Join-Path $env:APPDATA '1C\1CEStart\ibases.v8i'
}

function Get-1CInfoBaseList {
    $path = Get-1CInfoBaseRegistryPath
    if (-not (Test-Path -LiteralPath $path)) {
        return @()
    }

    $text = $null
    foreach ($encodingName in @('UTF8', 'Default')) {
        try {
            $text = Get-Content -LiteralPath $path -Raw -Encoding $encodingName
            break
        }
        catch {
            continue
        }
    }
    if (-not $text) {
        return @()
    }

    $items = New-Object System.Collections.Generic.List[object]
    $currentName = $null
    $currentConnect = $null
    $script:ibVersionByName = @{}

    foreach ($line in ($text -split "`r?`n")) {
        if ($line -match '^\[(.+)\]$') {
            if ($currentName -and $currentConnect) {
                $version = ''
                if ($script:ibVersionByName.ContainsKey($currentName)) {
                    $version = $script:ibVersionByName[$currentName]
                }
                $items.Add([PSCustomObject]@{
                    Name = $currentName
                    Connect = $currentConnect
                    Version = $version
                })
            }
            $currentName = $Matches[1]
            $currentConnect = $null
        }
        elseif ($line -match '^Connect=(.+)$') {
            $currentConnect = $Matches[1].Trim()
        }
        elseif ($line -match '^Version=(.+)$') {
            if ($null -ne $currentName) {
                $script:ibVersionByName = $script:ibVersionByName
                if (-not $script:ibVersionByName) {
                    $script:ibVersionByName = @{}
                }
                $script:ibVersionByName[$currentName] = $Matches[1].Trim()
            }
        }
    }

    if ($currentName -and $currentConnect) {
        $version = ''
        if ($script:ibVersionByName.ContainsKey($currentName)) {
            $version = $script:ibVersionByName[$currentName]
        }
        $items.Add([PSCustomObject]@{
            Name = $currentName
            Connect = $currentConnect
            Version = $version
        })
    }

    return [object[]]$items.ToArray()
}

function Get-1CInfoBaseVersionFromRegistry {
    param([Parameter(Mandatory = $true)][string]$InfoBaseName)

    $bases = Get-1CInfoBaseList
    foreach ($base in $bases) {
        if ([string]$base.Name -eq $InfoBaseName) {
            return [string]$base.Version
        }
    }

    return ''
}

function ConvertFrom-1CConnectString {
    param([Parameter(Mandatory = $true)][string]$Connect)

    $result = @{
        InfoBasePath = $null
        Server = $null
        Ref = $null
    }

    if ($Connect -match 'File="([^"]+)"') {
        $result.InfoBasePath = $Matches[1]
    }
    if ($Connect -match 'Srvr="([^"]+)"') {
        $result.Server = $Matches[1]
    }
    if ($Connect -match 'Ref="([^"]+)"') {
        $result.Ref = $Matches[1]
    }

    return $result
}

function Get-1CInfoBaseProperty {
    param(
        $Item,
        [Parameter(Mandatory = $true)][string[]]$Names
    )

    if ($null -eq $Item) {
        return $null
    }

    $propertyNames = $Item.PSObject.Properties.Name
    foreach ($propertyName in $Names) {
        if ($propertyNames -contains $propertyName) {
            return $Item.$propertyName
        }
    }

    return $null
}

function Get-1CCollectionCount {
    param($Value)

    if ($null -eq $Value) {
        return 0
    }

    return @($Value).Count
}
