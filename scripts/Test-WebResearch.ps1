# Smoke-тест веб-поиска (форумы + статус ИТС). Пароль ИТС не выводится.
param(
    [string]$ForumQuery = "заполнение серий перемещение материалов"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root "mcp\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Сначала: .\scripts\Setup-Mcp.ps1" -ForegroundColor Yellow
    exit 1
}

& $venvPython -m pip install -q httpx beautifulsoup4

$code = @'
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp"))

from web_research import search_forums_payload, web_research_status

status = web_research_status(ROOT)
print("=== web_research_status ===")
print(json.dumps(status, ensure_ascii=False, indent=2))

query = sys.argv[1] if len(sys.argv) > 1 else "1c синхронизация спецификации"
forums = search_forums_payload(
    ROOT,
    query,
    configuration_name="УправлениеНебольшойФирмой",
    configuration_version="3.0.13.305",
    limit=3,
)
print("\n=== onec_web_search_forums (sample) ===")
print(json.dumps(forums, ensure_ascii=False, indent=2))
'@

$tempPy = Join-Path $env:TEMP "test-web-research.py"
Set-Content -Path $tempPy -Encoding UTF8 -Value $code
& $venvPython $tempPy $ForumQuery
