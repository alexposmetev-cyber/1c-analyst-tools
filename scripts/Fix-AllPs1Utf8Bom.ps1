#Requires -Version 5.1
<#
.SYNOPSIS
    Добавляет UTF-8 BOM ко всем .ps1 проекта (нужно для Windows PowerShell 5.1 + кириллица).
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path $PSScriptRoot -Parent
$utf8Bom = New-Object System.Text.UTF8Encoding $true
$fixed = 0

Get-ChildItem -LiteralPath $Root -Recurse -Filter *.ps1 -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\node_modules\\|\\\.venv\\|\\Obsidian\\|\\\.Obsidian\\' } |
    ForEach-Object {
        $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) {
            return
        }

        $content = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)
        [System.IO.File]::WriteAllText($_.FullName, $content, $utf8Bom)
        $fixed++
        Write-Host "BOM: $($_.FullName)"
    }

Write-Host "Done. Updated files: $fixed"
