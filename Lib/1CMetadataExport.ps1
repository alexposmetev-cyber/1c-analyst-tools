#Requires -Version 5.1
Set-StrictMode -Version Latest

$script:1CComAccessPath = Join-Path $PSScriptRoot '1CComAccess.ps1'
if (-not (Get-Command Get-1CComProperty -ErrorAction SilentlyContinue)) {
    . $script:1CComAccessPath
}

function Get-1CSafePathSegment {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return 'unknown'
    }

    $result = $Text.Trim()
    foreach ($char in [System.IO.Path]::GetInvalidFileNameChars()) {
        $result = $result.Replace([string]$char, '_')
    }

    return ($result -replace '\s+', '_')
}

function Get-1CMetadataSynonym {
    param(
        $Connection,
        $MetaObject
    )

    if ($null -eq $MetaObject) {
        return ''
    }

    try {
        $value = Convert-1CComString -Connection $Connection -Value (Get-1CComProperty -ComObject $MetaObject -Name 'Synonym')
        if ([string]::IsNullOrWhiteSpace($value)) {
            return ''
        }
        return $value
    }
    catch {
        return ''
    }
}

function Get-1CMetadataMemberNames {
    param($Members)

    $names = New-Object System.Collections.Generic.List[string]
    if ($null -eq $Members) {
        return @()
    }

    foreach ($member in $Members) {
        if ($null -eq $member) { continue }
        $names.Add([string](Get-1CComProperty -ComObject $member -Name 'Name'))
    }

    return $names.ToArray()
}

function Get-1CMetadataTabularParts {
    param(
        $Connection,
        $MetaObject
    )

    $parts = @()
    $sections = $null
    try {
        $sections = Get-1CComProperty -ComObject $MetaObject -Name 'TabularSections'
    }
    catch {
        return $parts
    }

    if ($null -eq $sections) {
        return $parts
    }

    foreach ($section in $sections) {
        $parts += [ordered]@{
            name = [string](Get-1CComProperty -ComObject $section -Name 'Name')
            synonym = (Get-1CMetadataSynonym -Connection $Connection -MetaObject $section)
            attributes = @(Get-1CMetadataMemberNames -Members (Get-1CComProperty -ComObject $section -Name 'Attributes'))
        }
    }

    return $parts
}

function Get-1CMetadataCacheKey {
    param(
        $Connection,
        [string]$InfoBasePath,
        [string]$Server,
        [string]$Ref
    )

    $metadata = Get-1CConnectionMetadata -Connection $Connection
    $configurationInfo = Get-1CConfigurationInfo -Connection $Connection -Metadata $metadata `
        -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref
    $configName = [string]$configurationInfo.Name
    $configVersion = [string]$configurationInfo.Version

    if ($InfoBasePath) {
        $baseKey = Split-Path -Path $InfoBasePath -Leaf
    }
    elseif ($Server -and $Ref) {
        $baseKey = "${Server}_${Ref}"
    }
    else {
        $baseKey = 'base'
    }

    $segments = @(
        (Get-1CSafePathSegment -Text $baseKey)
        (Get-1CSafePathSegment -Text $configName)
        (Get-1CSafePathSegment -Text $configVersion)
    )

    return ($segments -join '__')
}

function Get-1CMetadataCollectionMap {
    return @(
        @{ Property = 'Documents'; Type = 'Document'; Prefix = 'Документ' }
        @{ Property = 'Catalogs'; Type = 'Catalog'; Prefix = 'Справочник' }
        @{ Property = 'Enums'; Type = 'Enum'; Prefix = 'Перечисление' }
        @{ Property = 'AccumulationRegisters'; Type = 'AccumulationRegister'; Prefix = 'РегистрНакопления' }
        @{ Property = 'InformationRegisters'; Type = 'InformationRegister'; Prefix = 'РегистрСведений' }
        @{ Property = 'AccountingRegisters'; Type = 'AccountingRegister'; Prefix = 'РегистрБухгалтерии' }
        @{ Property = 'Constants'; Type = 'Constant'; Prefix = 'Константа' }
        @{ Property = 'Reports'; Type = 'Report'; Prefix = 'Отчет' }
        @{ Property = 'DataProcessors'; Type = 'DataProcessor'; Prefix = 'Обработка' }
    )
}

function Get-1CMetadataMembersSafe {
    param(
        $MetaObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    try {
        return @(Get-1CMetadataMemberNames -Members (Get-1CComProperty -ComObject $MetaObject -Name $PropertyName))
    }
    catch {
        return @()
    }
}

function Export-1CMetadataObjectCard {
    param(
        $Connection,
        [string]$Type,
        [string]$Prefix,
        $MetaObject
    )

    $fullName = "$Prefix.$((Get-1CComProperty -ComObject $MetaObject -Name 'Name'))"
    $card = [ordered]@{
        type = $Type
        name = [string](Get-1CComProperty -ComObject $MetaObject -Name 'Name')
        fullName = $fullName
        synonym = (Get-1CMetadataSynonym -Connection $Connection -MetaObject $MetaObject)
        attributes = @(Get-1CMetadataMembersSafe -MetaObject $MetaObject -PropertyName 'Attributes')
    }

    if ($Type -in @('Document', 'Catalog')) {
        $card.tabularParts = @(Get-1CMetadataTabularParts -Connection $Connection -MetaObject $MetaObject)
    }

    if ($Type -in @('AccumulationRegister', 'InformationRegister', 'AccountingRegister')) {
        $card.dimensions = @(Get-1CMetadataMembersSafe -MetaObject $MetaObject -PropertyName 'Dimensions')
        $card.resources = @(Get-1CMetadataMembersSafe -MetaObject $MetaObject -PropertyName 'Resources')
    }

    return $card
}

function Test-1CMetadataCacheFresh {
    param(
        [string]$ManifestPath,
        [string]$ExpectedCacheKey,
        [int]$MaxAgeHours = 168
    )

    if (-not (Test-Path -LiteralPath $ManifestPath)) {
        return $false
    }

    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $false
    }

    if ($manifest.cacheKey -ne $ExpectedCacheKey) {
        return $false
    }

    if (-not $manifest.exportedAt) {
        return $false
    }

    $exportedAt = [datetime]::Parse($manifest.exportedAt)
    $age = (Get-Date) - $exportedAt
    return ($age.TotalHours -le $MaxAgeHours)
}

function Test-1CMetadataVersionKnown {
    param([string]$Version)

    $normalized = [string]$Version
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return $false
    }

    return ($normalized.Trim().ToLowerInvariant() -ne 'unknown')
}

function Export-1CMetadataToCache {
    param(
        $Connection,
        [string]$CacheRoot,
        [string]$InfoBasePath,
        [string]$Server,
        [string]$Ref,
        [switch]$Force
    )

    $cacheKey = Get-1CMetadataCacheKey -Connection $Connection -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref
    $cacheDir = Join-Path $CacheRoot $cacheKey
    $objectsDir = Join-Path $cacheDir 'objects'
    $manifestPath = Join-Path $cacheDir 'manifest.json'
    $indexPath = Join-Path $cacheDir 'index.json'

    if (-not $Force -and (Test-1CMetadataCacheFresh -ManifestPath $manifestPath -ExpectedCacheKey $cacheKey)) {
        $existing = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (Test-1CMetadataVersionKnown -Version ([string]$existing.version)) {
            return [pscustomobject]@{
                cacheKey = $cacheKey
                cachePath = $cacheDir
                cacheRelative = (Get-1CMetadataRelativePath -CacheRoot $CacheRoot -CacheDir $cacheDir)
                configurationName = [string]$existing.configurationName
                configurationSynonym = [string]$existing.configurationSynonym
                version = [string]$existing.version
                objectCount = [int]$existing.objectCount
                exportedAt = [string]$existing.exportedAt
                reused = $true
            }
        }
    }

    if (Test-Path -LiteralPath $cacheDir) {
        Remove-Item -LiteralPath $cacheDir -Recurse -Force
    }

    New-Item -ItemType Directory -Path $objectsDir -Force | Out-Null

    $metadata = Get-1CConnectionMetadata -Connection $Connection
    $configurationInfo = Get-1CConfigurationInfo -Connection $Connection -Metadata $metadata `
        -InfoBasePath $InfoBasePath -Server $Server -Ref $Ref
    $indexItems = New-Object System.Collections.Generic.List[object]
    $collectionMap = Get-1CMetadataCollectionMap

    foreach ($entry in $collectionMap) {
        $collection = $null
        try {
            $collection = Get-1CComProperty -ComObject $metadata -Name $entry.Property
        }
        catch {
            continue
        }

        if ($null -eq $collection) { continue }

        foreach ($metaObject in $collection) {
            $card = Export-1CMetadataObjectCard -Connection $Connection -Type $entry.Type -Prefix $entry.Prefix -MetaObject $metaObject
            $indexItems.Add([ordered]@{
                type = $card.type
                name = $card.name
                fullName = $card.fullName
                synonym = $card.synonym
            })

            $objectPath = Join-Path $objectsDir ("$($card.fullName).json")
            ($card | ConvertTo-Json -Depth 6 -Compress) | Out-File -LiteralPath $objectPath -Encoding UTF8
        }
    }

    $exportedAt = (Get-Date).ToString('o')
    $target = if ($InfoBasePath) { $InfoBasePath } else { "$Server / $Ref" }
    $configVersion = [string]$configurationInfo.Version

    $manifest = [ordered]@{
        cacheKey = $cacheKey
        cachePath = $cacheDir
        cacheRelative = (Get-1CMetadataRelativePath -CacheRoot $CacheRoot -CacheDir $cacheDir)
        configurationName = [string]$configurationInfo.Name
        configurationSynonym = [string]$configurationInfo.Synonym
        version = $configVersion
        exportedAt = $exportedAt
        target = $target
        objectCount = $indexItems.Count
    }

    ($indexItems.ToArray() | ConvertTo-Json -Depth 4 -Compress) | Out-File -LiteralPath $indexPath -Encoding UTF8
    ($manifest | ConvertTo-Json -Depth 4 -Compress) | Out-File -LiteralPath $manifestPath -Encoding UTF8

    return [pscustomobject]@{
        cacheKey = $cacheKey
        cachePath = $cacheDir
        cacheRelative = $manifest.cacheRelative
        configurationName = $manifest.configurationName
        configurationSynonym = $manifest.configurationSynonym
        version = $manifest.version
        objectCount = [int]$manifest.objectCount
        exportedAt = $exportedAt
        reused = $false
    }
}

function Get-1CMetadataRelativePath {
    param(
        [string]$CacheRoot,
        [string]$CacheDir
    )

    $rootFull = [System.IO.Path]::GetFullPath($CacheRoot)
    $dirFull = [System.IO.Path]::GetFullPath($CacheDir)

    if ($dirFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $dirFull.Substring($rootFull.Length).TrimStart('\', '/').Replace('\', '/')
    }

    return $CacheDir
}

function Write-1CMetadataExportResult {
    param(
        $Result,
        [string]$Format = 'Json'
    )

    $payload = [ordered]@{
        status = 'ok'
        ready = $true
        reused = [bool]$Result.reused
        cacheKey = $Result.cacheKey
        cachePath = $Result.cacheRelative
        configurationName = $Result.configurationName
        configurationSynonym = $Result.configurationSynonym
        version = $Result.version
        objectCount = $Result.objectCount
        exportedAt = $Result.exportedAt
        fingerprint = "$($Result.configurationName)|$($Result.version)|$($Result.objectCount)"
    }

    if ($Format -eq 'Json') {
        Write-Output ($payload | ConvertTo-Json -Depth 4 -Compress)
        return
    }

    Write-Output ($payload | ConvertTo-Json -Depth 4)
}
