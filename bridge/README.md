# 1C Bridge Agent (MVP)

Долгоживущий COM-мост между информационной базой 1С и оркестратором (очередь jobs).

## Компоненты

| Компонент | Назначение |
|-----------|------------|
| `orchestrator/app.py` | FastAPI: poll, result, enqueue |
| `agent/Bridge-Agent.ps1` | COM-сессия + цикл poll |
| `agent/BridgeCom.ps1` | Подключение и read-only запросы |

## Быстрый старт (DemoTrd)

### 1. COM (один раз)

```bat
Register-1CCom.cmd
```

### 2. Конфиг агента

```powershell
copy bridge\agent\bridge-agent.json.example bridge\agent\bridge-agent.json
```

По умолчанию в example: `C:\Users\aaposmetev\Documents\1C\DemoTrd`, `bridge_id=demotrd`.

Укажите `connection.user` и `connection.password`, если пустой пользователь не подходит (ошибка COM: неверный логин/пароль). Для внешнего соединения у пользователя 1С должно быть разрешено **внешнее (COM) подключение**.

После правки `.ps1` при ошибках кодировки:

```powershell
.\scripts\Fix-Utf8Bom.ps1 -Path .\bridge\agent\Bridge-Agent.ps1
.\scripts\Fix-Utf8Bom.ps1 -Path .\bridge\agent\BridgeCom.ps1
```

### 3. Терминал 1 — оркестратор

```bat
bridge\Start-Orchestrator.cmd
```

Проверка: http://127.0.0.1:8787/health

### 4. Терминал 2 — агент

```bat
bridge\Start-BridgeAgent.cmd
```

В логе: `COM подключён`, затем `Ожидание jobs`.

### 5. Терминал 3 — тест

```powershell
.\bridge\Test-EnqueueJob.ps1
```

Или ping:

```powershell
.\bridge\Test-EnqueueJob.ps1 -Tool ping -Query ''
```

## API

| Метод | URL |
|-------|-----|
| GET | `/health` |
| GET | `/api/bridge/poll?bridge_id=&bridge_token=&wait_sec=25` |
| POST | `/api/bridge/result` |
| POST | `/api/bridge/enqueue` |
| GET | `/api/jobs/{job_id}` |
| GET | `/api/bridges` |

### enqueue (пример)

```json
{
  "bridge_id": "demotrd",
  "bridge_token": "change-me-local-demo-token",
  "tool": "execute_query",
  "arguments": {
    "query": "ВЫБРАТЬ 1 КАК N",
    "max_rows": 500
  }
}
```

Tools: `execute_query` (только ВЫБРАТЬ), `ping`.

## OpenCode / MCP onec-data

При запущенном оркестраторе и Bridge-Agent инструменты MCP используют мост автоматически:

| MCP | Через Bridge | Fallback |
|-----|--------------|----------|
| `onec_query` | да, если ИБ совпадает с `bridge-agent.json` | Get-1CData.ps1 |
| `onec_connect` / `onec_check_connection` | ping через Bridge | COM |
| `onec_bridge_status` | диагностика | — |

Конфиг моста: `bridge/agent/bridge-agent.json` или корневой `.onec-bridge.json`.

Быстрый старт OpenCode (Bridge поднимается автоматически):

```bat
Start-OpenCode.cmd
```

Проверка из Python (тот же venv, что MCP):

```powershell
mcp\.venv\Scripts\python.exe -c "from mcp.bridge_client import bridge_status_payload; import json; print(json.dumps(bridge_status_payload(), ensure_ascii=False, indent=2))"
```

## Отличие от прямого COM в MCP

Агент держит **одно** COM-соединение и переподключается при ошибке. Без Bridge MCP вызывает `Get-1CData.ps1` с `ReleaseComObject` на каждый запрос.

## Секреты

`bridge/agent/bridge-agent.json` в `.gitignore` — не коммитить пароли.
