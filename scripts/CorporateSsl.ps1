#Requires -Version 5.1
<#
.SYNOPSIS
    Общие функции обхода корпоративного SSL (MITM-прокси, корневой сертификат организации).
#>
Set-StrictMode -Version Latest

function Get-CorporateSslManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $path = Join-Path $ProjectRoot 'install\corporate-ssl.json'
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Warning "Не удалось прочитать install\corporate-ssl.json: $($_.Exception.Message)"
        return $null
    }
}

function Test-CorporateSslEnabled {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $manifest = Get-CorporateSslManifest -ProjectRoot $ProjectRoot
    if (-not $manifest) {
        return $false
    }

    return [bool]$manifest.enabled
}

function Enable-CorporateSslProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $manifest = Get-CorporateSslManifest -ProjectRoot $ProjectRoot
    if (-not $manifest -or -not $manifest.enabled) {
        return $false
    }

    if ($manifest.environment) {
        foreach ($property in $manifest.environment.PSObject.Properties) {
            Set-Item -Path "Env:$($property.Name)" -Value ([string]$property.Value)
        }
    }

    if ($manifest.powershell_skip_certificate_check) {
        Enable-CorporateTlsBypassForPowerShell
    }

    return $true
}

function Enable-CorporateSslUser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $manifest = Get-CorporateSslManifest -ProjectRoot $ProjectRoot
    if (-not $manifest -or -not $manifest.enabled) {
        return $false
    }

    if ($manifest.environment) {
        foreach ($property in $manifest.environment.PSObject.Properties) {
            [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'User')
        }
    }

    return $true
}

function Disable-CorporateSslUser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $manifest = Get-CorporateSslManifest -ProjectRoot $ProjectRoot
    if (-not $manifest -or -not $manifest.environment) {
        return
    }

    foreach ($property in $manifest.environment.PSObject.Properties) {
        [Environment]::SetEnvironmentVariable($property.Name, $null, 'User')
    }
}

function Enable-CorporateTlsBypassForPowerShell {
    if (-not ([System.Management.Automation.PSTypeName]'TrustAllCertsPolicy').Type) {
        Add-Type @"
using System.Net;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy {
    public static bool Validate(
        object sender,
        X509Certificate certificate,
        X509Chain chain,
        SslPolicyErrors sslPolicyErrors) {
        return true;
    }
}
"@
    }

    $protocols = [System.Net.SecurityProtocolType]::Tls12
    if ([enum]::IsDefined([type][System.Net.SecurityProtocolType], 'Tls13')) {
        $protocols = $protocols -bor [System.Net.SecurityProtocolType]::Tls13
    }
    [System.Net.ServicePointManager]::SecurityProtocol = $protocols
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = `
        { [TrustAllCertsPolicy]::Validate($args[0], $args[1], $args[2], $args[3]) }
}

function Ensure-OneCWebConfigForCorporateSsl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,

        [bool]$VerifySsl = $false
    )

    $configPath = Join-Path $ProjectRoot '.onec-web.json'
    $examplePath = Join-Path $ProjectRoot '.onec-web.json.example'
    $payload = [ordered]@{
        verify_ssl = $VerifySsl
    }

    if (Test-Path -LiteralPath $configPath) {
        try {
            $existing = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($existing -is [pscustomobject]) {
                $hash = @{}
                $existing.PSObject.Properties | ForEach-Object { $hash[$_.Name] = $_.Value }
                $hash['verify_ssl'] = $VerifySsl
                $payload = $hash
            }
        }
        catch {
            Write-Warning "Не удалось обновить .onec-web.json: $($_.Exception.Message)"
        }
    }
    elseif (Test-Path -LiteralPath $examplePath) {
        try {
            $existing = Get-Content -LiteralPath $examplePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($existing -is [pscustomobject]) {
                $hash = @{}
                $existing.PSObject.Properties | ForEach-Object { $hash[$_.Name] = $_.Value }
                $hash['verify_ssl'] = $VerifySsl
                $payload = $hash
            }
        }
        catch {
            Write-Warning "Не удалось прочитать .onec-web.json.example: $($_.Exception.Message)"
        }
    }

    ($payload | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $configPath -Encoding UTF8
}

function Install-CorporateSslProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,

        [switch]$PersistUserEnv
    )

    if (-not (Test-CorporateSslEnabled -ProjectRoot $ProjectRoot)) {
        Write-Host '   Пропуск: install\corporate-ssl.json отключён (enabled=false)'
        return $false
    }

    $manifest = Get-CorporateSslManifest -ProjectRoot $ProjectRoot
    $verifySsl = $true
    if ($null -ne $manifest.verify_ssl) {
        $verifySsl = [bool]$manifest.verify_ssl
    }

    Enable-CorporateSslProcess -ProjectRoot $ProjectRoot | Out-Null
    if ($PersistUserEnv) {
        Enable-CorporateSslUser -ProjectRoot $ProjectRoot | Out-Null
    }

    Ensure-OneCWebConfigForCorporateSsl -ProjectRoot $ProjectRoot -VerifySsl:$verifySsl
    Write-Host "   OK: корпоративный SSL (verify_ssl=$verifySsl, ONEC_WEB_VERIFY_SSL=$($env:ONEC_WEB_VERIFY_SSL))"
    return $true
}
