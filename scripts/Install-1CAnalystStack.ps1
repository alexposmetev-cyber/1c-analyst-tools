#Requires -Version 5.1
<#
.SYNOPSIS
    Установка стека 1C Analyst Tools: Python, MCP, OpenCode, Obsidian.

.PARAMETER RegisterCom
    Зарегистрировать COM 1С (UAC). Требуется установленная платформа 1С.

.EXAMPLE
    .\scripts\Install-1CAnalystStack.ps1

.EXAMPLE
    .\scripts\Install-1CAnalystStack.ps1 -RegisterCom
#>
[CmdletBinding()]
param(
    [switch]$SkipObsidian,
    [switch]$SkipGit,
    [switch]$SkipOpenCode,
    [switch]$RegisterCom
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path $PSScriptRoot -Parent
$ManifestPath = Join-Path $ProjectRoot 'install\manifest.json'
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($machine -and $user) {
        $env:Path = "$machine;$user"
    }
}

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-WingetPackageInstalled {
    param([string]$PackageId)
    if (-not (Test-CommandAvailable 'winget')) {
        return $false
    }
    $output = & winget list --id $PackageId -e --source winget --accept-source-agreements 2>&1 | Out-String
    return $output -match [regex]::Escape($PackageId)
}

function Install-WingetPackage {
    param(
        [string]$PackageId,
        [string]$DisplayName
    )
    if (Test-WingetPackageInstalled -PackageId $PackageId) {
        Write-Host "   OK: $DisplayName уже установлен ($PackageId)"
        return
    }
    if (-not (Test-CommandAvailable 'winget')) {
        throw "winget не найден. Установите App Installer из Microsoft Store или пакеты вручную: $DisplayName ($PackageId)"
    }
    Write-Host "   Установка $DisplayName через winget (источник winget)..."
    & winget install --id $PackageId -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -gt 1) {
        throw "winget install $PackageId завершился с кодом $LASTEXITCODE"
    }
    Refresh-Path
}

function Get-PythonExecutable {
    Refresh-Path
    if (Test-CommandAvailable 'py') {
        try {
            $version = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
            if ($version) {
                return $version.Trim()
            }
        }
        catch {
            # py launcher bez Python 3.12
        }
    }
    if (Test-CommandAvailable 'python') {
        try {
            $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($version -and ([version]$version.Trim() -ge [version]'3.10')) {
                return (Get-Command python).Source
            }
        }
        catch {
            # python ne v PATH ili sloman
        }
    }

    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    foreach ($folder in @('Python312', 'Python311', 'Python310')) {
        $candidate = Join-Path $localAppData "Programs\Python\$folder\python.exe"
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $null
}

function Ensure-Python {
    $python = Get-PythonExecutable
    if ($python) {
        Write-Host "   OK: Python — $python"
        return $python
    }
    Install-WingetPackage -PackageId $Manifest.winget.python.id -DisplayName $Manifest.winget.python.name
    Refresh-Path
    $python = Get-PythonExecutable
    if (-not $python) {
        throw "Python 3.10+ не найден после установки. Перезапустите терминал и повторите Install.cmd"
    }
    Write-Host "   OK: Python — $python"
    return $python
}

function Ensure-ProjectConfig {
    $localConfig = Join-Path $ProjectRoot 'opencode.local.json'
    $example = Join-Path $ProjectRoot 'opencode.local.json.example'
    if (Test-Path -LiteralPath $localConfig) {
        Write-Host "   OK: opencode.local.json уже есть"
        return
    }
    if (-not (Test-Path -LiteralPath $example)) {
        throw "Не найден opencode.local.json.example"
    }

    Copy-Item -LiteralPath $example -Destination $localConfig
    Write-Host "   Создан opencode.local.json — задайте ONEBITAI_API_KEY (scripts\Set-1bitApiKey.ps1)"
}

function Ensure-ObsidianVault {
    $vault = Join-Path $ProjectRoot '.Obsidian'
    if (-not (Test-Path -LiteralPath $vault)) {
        New-Item -ItemType Directory -Path $vault | Out-Null
        Write-Host "   Создан каталог .Obsidian/"
    }
    else {
        Write-Host "   OK: .Obsidian/"
    }
}

function Ensure-ExecutionPolicy {
    $current = Get-ExecutionPolicy -Scope CurrentUser
    if ($current -eq 'Undefined' -or $current -eq 'Restricted') {
        try {
            Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
            Write-Host "   ExecutionPolicy CurrentUser -> RemoteSigned"
        }
        catch {
            Write-Host "   !! ExecutionPolicy ne izmenen (politika organizacii). Ispolzuyte .cmd-launchery." -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "   OK: ExecutionPolicy CurrentUser = $current"
    }
}

Write-Host "1C Analyst Tools — установка" -ForegroundColor Green
Write-Host "Каталог: $ProjectRoot"

Write-Step "Политика PowerShell"
Ensure-ExecutionPolicy

Write-Step "Git (опционально)"
if ($SkipGit) {
    Write-Host "   Пропуск"
}
elseif (Test-CommandAvailable 'git') {
    Write-Host "   OK: git в PATH"
}
else {
    Install-WingetPackage -PackageId $Manifest.winget.git.id -DisplayName $Manifest.winget.git.name
}

Write-Step "Python и MCP venv"
$pythonExe = Ensure-Python
$setupMcp = Join-Path $ProjectRoot 'scripts\Setup-Mcp.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setupMcp
if ($LASTEXITCODE -ne 0) {
    throw "Setup-Mcp.ps1 завершился с ошибкой"
}

Write-Step "OpenCode"
if ($SkipOpenCode) {
    Write-Host "   Пропуск"
}
else {
    $updateScript = Join-Path $ProjectRoot 'scripts\Update-OpenCode.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $updateScript
    if ($LASTEXITCODE -ne 0) {
        throw "Update-OpenCode.ps1 завершился с ошибкой"
    }
}

Write-Step "Obsidian"
if ($SkipObsidian) {
    Write-Host "   Пропуск"
}
else {
    Install-WingetPackage -PackageId $Manifest.winget.obsidian.id -DisplayName $Manifest.winget.obsidian.name
    Ensure-ObsidianVault
}

Write-Step "Конфигурация LLM"
Write-Host "   Установщик не ставит LLM — настройте endpoint в opencode.local.json"
Ensure-ProjectConfig

Write-Step "COM 1С"
if ($RegisterCom) {
    $registerCmd = Join-Path $ProjectRoot 'Register-1CCom.cmd'
    if (-not (Test-Path -LiteralPath $registerCmd)) {
        throw "Не найден Register-1CCom.cmd"
    }
    & $registerCmd
}
else {
    Write-Host "   Пропуск (добавьте -RegisterCom после установки платформы 1С)"
}

Write-Step "Проверка"
$checks = @(
    @{ Name = 'Python venv'; Path = Join-Path $ProjectRoot 'mcp\.venv\Scripts\python.exe' },
    @{ Name = 'MCP server'; Path = Join-Path $ProjectRoot 'mcp\server.py' },
    @{ Name = 'OpenCode'; Path = Join-Path $ProjectRoot 'bin\opencode.exe' },
    @{ Name = 'opencode.local.json'; Path = Join-Path $ProjectRoot 'opencode.local.json' }
)
foreach ($check in $checks) {
    if ($SkipOpenCode -and $check.Name -eq 'OpenCode') {
        continue
    }
    if (Test-Path -LiteralPath $check.Path) {
        Write-Host "   OK: $($check.Name)"
    }
    else {
        Write-Host "   !!: $($check.Name) - ne naiden" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Установка завершена." -ForegroundColor Green
Write-Host ""
Write-Host "Дальше:"
Write-Host "  1. COM 1С (один раз, админ Windows или IT):  .\Register-1CCom.cmd"
Write-Host "  2. API 1bit AI:         .\scripts\Set-1bitApiKey.ps1  (klyuch kompanii)"
Write-Host "  3. Bridge (опционально): copy bridge\agent\bridge-agent.json.example bridge\agent\bridge-agent.json"
Write-Host "  4. Запуск агента:       .\Start-OpenCode.cmd  (Bridge стартует автоматически)"
Write-Host "  5. Smoke-test:          .\scripts\Test-AnalystStack.ps1"
Write-Host ""
