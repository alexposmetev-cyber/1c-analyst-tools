#Requires -Version 5.1
Set-StrictMode -Version Latest

function Get-1CComProperty {
    param(
        [Parameter(Mandatory = $true)]
        $ComObject,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq $ComObject) {
        throw "COM-объект не задан (свойство '$Name')."
    }

    return $ComObject.GetType().InvokeMember(
        $Name,
        [System.Reflection.BindingFlags]::GetProperty,
        $null,
        $ComObject,
        $null
    )
}

function Invoke-1CComMethod {
    param(
        [Parameter(Mandatory = $true)]
        $ComObject,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        $Arguments = @()
    )

    if ($null -eq $ComObject) {
        throw "COM-объект не задан (метод '$Name')."
    }

    return $ComObject.GetType().InvokeMember(
        $Name,
        [System.Reflection.BindingFlags]::InvokeMethod,
        $null,
        $ComObject,
        $Arguments
    )
}

function Get-1CConnectionMetadata {
    param(
        [Parameter(Mandatory = $true)]
        $Connection
    )

    return Get-1CComProperty -ComObject $Connection -Name 'Metadata'
}

function Convert-1CComString {
    param(
        [Parameter(Mandatory = $true)]
        $Connection,
        $Value
    )

    if ($null -eq $Value) {
        return $null
    }

    $stringValue = Invoke-1CComMethod -ComObject $Connection -Name 'String' -Arguments @($Value)
    if ($stringValue -eq 'NULL' -or $stringValue -eq 'Неопределено') {
        return $null
    }

    return [string]$stringValue
}

function Get-1CComPropertyAsString {
    param(
        [Parameter(Mandatory = $true)]
        $Connection,
        [Parameter(Mandatory = $true)]
        $ComObject,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq $ComObject) {
        return ''
    }

    try {
        $raw = Get-1CComProperty -ComObject $ComObject -Name $Name
    }
    catch {
        return ''
    }

    if ($null -eq $raw) {
        return ''
    }

    try {
        $converted = Convert-1CComString -Connection $Connection -Value $raw
        if (-not [string]::IsNullOrWhiteSpace($converted)) {
            return $converted.Trim()
        }
    }
    catch {
        # fallback to CLR string below
    }

    return ([string]$raw).Trim()
}

function Read-1CConfigurationFieldsFromObject {
    param(
        [Parameter(Mandatory = $true)]
        $Connection,
        [Parameter(Mandatory = $true)]
        $ComObject,
        [ref]$Name,
        [ref]$Synonym,
        [ref]$Version
    )

    foreach ($propertyName in @('Name')) {
        if (-not [string]::IsNullOrWhiteSpace($Name.Value)) {
            break
        }

        $value = Get-1CComPropertyAsString -Connection $Connection -ComObject $ComObject -Name $propertyName
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $Name.Value = $value
        }
    }

    foreach ($propertyName in @('Synonym')) {
        if (-not [string]::IsNullOrWhiteSpace($Synonym.Value)) {
            break
        }

        $value = Get-1CComPropertyAsString -Connection $Connection -ComObject $ComObject -Name $propertyName
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $Synonym.Value = $value
        }
    }

    foreach ($propertyName in @('Version')) {
        if (-not [string]::IsNullOrWhiteSpace($Version.Value)) {
            break
        }

        $value = Get-1CComPropertyAsString -Connection $Connection -ComObject $ComObject -Name $propertyName
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $Version.Value = $value
        }
    }
}

function Get-1CConfigurationInfo {
    param(
        $Connection,
        $Metadata,
        [string]$InfoBasePath,
        [string]$Server,
        [string]$Ref
    )

    $name = ''
    $synonym = ''
    $version = ''

    Read-1CConfigurationFieldsFromObject -Connection $Connection -ComObject $Metadata `
        -Name ([ref]$name) -Synonym ([ref]$synonym) -Version ([ref]$version)

    foreach ($propertyName in @('Configuration', 'MainConfiguration')) {
        try {
            $configuration = Get-1CComProperty -ComObject $Metadata -Name $propertyName
            if ($null -eq $configuration) {
                continue
            }

            Read-1CConfigurationFieldsFromObject -Connection $Connection -ComObject $configuration `
                -Name ([ref]$name) -Synonym ([ref]$synonym) -Version ([ref]$version)

            if (-not [string]::IsNullOrWhiteSpace($name) -and -not [string]::IsNullOrWhiteSpace($version)) {
                break
            }
        }
        catch {
            continue
        }
    }

    if ([string]::IsNullOrWhiteSpace($name)) {
        if ($InfoBasePath) {
            $name = Split-Path -Path $InfoBasePath -Leaf
        }
        elseif ($Server -and $Ref) {
            $name = $Ref
        }
        else {
            $name = 'UnknownConfig'
        }
    }

    return [ordered]@{
        Name = $name
        Synonym = $synonym
        Version = $version
    }
}
