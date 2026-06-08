#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$utf8Bom = New-Object System.Text.UTF8Encoding $true
$content = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($Path, $content, $utf8Bom)
