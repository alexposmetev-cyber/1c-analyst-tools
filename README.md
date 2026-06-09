# 1C Analyst Tools

Read-only доступ к данным 1С и консультации **с базой, без базы и по общим вопросам** (ИТС, форумы) через **OpenCode** и локальную LLM.

## Установка одной командой (Windows)

**Требования:** Windows 10/11, [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/), платформа 1С 8.3/8.5 (для live-режима).

```powershell
git clone https://github.com/alexposmetev-cyber/1c-analyst-tools.git
cd 1c-analyst-tools
.\Install.cmd
```

Скрипт через winget установит **Python 3.12**, **Obsidian**, скачает **OpenCode** в `bin\`, создаст MCP venv и `opencode.local.json`. **LLM не устанавливается** — endpoint настраивается вручную.

| Параметр | Назначение |
|----------|------------|
| `-SkipObsidian` | Не ставить Obsidian |
| `-RegisterCom` | Сразу зарегистрировать COM 1С (UAC) |

```powershell
.\Install.cmd -RegisterCom
```

**После установки:**

1. `.\Register-1CCom.cmd` — если не использовали `-RegisterCom`
2. API-ключ компании: `.\scripts\Set-1bitApiKey.ps1` (или переменная `ONEBITAI_API_KEY`)
3. `.\Start-OpenCode.cmd` — веб-интерфейс OpenCode + агент **1c-analyst**, модель **1bitai/qwen3-coder**

Публикация на GitHub: репозиторий = корень этой папки; секреты (`opencode.local.json`, `.onec-*`) в `.gitignore`.

**Ошибка winget / msstore / сертификат** (корпоративная сеть): установщик использует только `--source winget`. Если Python уже ставили вручную — закройте cmd и снова запустите `Install.cmd`.

## Архитектура

```
Аналитик → OpenCode (agent 1c-analyst)
                ↓
         режим: live | offline | research  (skill 1c-work-modes)
                ↓
    live:  onec_connect → метаданные → ИТС → (код из XML-исходников) → onec_query по согласию
    offline/research: кейсы, ИТС, форумы (без подключения к ИБ)
                ↓
    Obsidian vault: Cases / Requirements / Sessions (MCP onec_obsidian_*)
```

## Obsidian

Агент сохраняет артефакты в `1c-analyst-tools/.Obsidian/{ИмяБазы}/` (каталог создаётся автоматически):

| Папка | MCP |
|-------|-----|
| `Cases/` | `onec_save_case` (draft/final, дополнение по `case_id`) |
| `Requirements/` | `onec_obsidian_save_requirements` |
| `Sessions/` | `onec_obsidian_save_session` + `onec_obsidian_append_session` |

Папка базы: из `onec_connect` или `database_name`. Подпапка `Справочники/` — справка по конфигурации для ЛТ.

Подключение: **не** передавать `platform_version` — авто по версии ИБ и `1cestart.cfg`; при ошибке COM — `Register-1CCom.cmd`.

## Требования

- Windows, PowerShell 5.1+, winget
- Платформа 1С **8.3 и/или 8.5**, зарегистрированный COM (`Register-1CCom.cmd`)
- Python 3.10+ (ставится установщиком)
- OpenCode 1.16+ (скачивается в `bin\` установщиком)
- Локальная или корпоративная LLM с **tool calling** (настраивается пользователем в `opencode.local.json`)

## Быстрый старт (вручную)

Если уже выполнили `.\Install.cmd`, переходите к шагу **COM** (при необходимости) и **Запуск**.

### 1. COM (один раз)

> **ExecutionPolicy блокирует `.ps1`?** Не запускайте `Register-1CCom.ps1` напрямую — используйте **`Register-1CCom.cmd`** (обходит политику).

**Рекомендуется (из PowerShell или cmd):**

```powershell
cd "d:\старый ноут\Cursor\1c-analyst-tools"
.\Register-1CCom.cmd
```

**Альтернатива в PowerShell одной строкой:**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\Register-1CCom.ps1"
```

**Разрешить скрипты для текущего пользователя (один раз, опционально):**

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

После этого можно вызывать `.\Register-1CCom.ps1` напрямую.

Если платформа не находится автоматически — **не используйте `$env:LOCALAPPDATA`**, если 1С установлена под другим профилем Windows. Посмотрите путь в конфиге 1С:

```powershell
Select-String InstalledLocation "$env:APPDATA\1C\1CEStart\1cestart.cfg"
```

Затем укажите полный путь к `bin`, например:

```powershell
.\Register-1CCom.cmd -PlatformPath "C:\Users\aaposmetev\AppData\Local\Programs\1cv8_x64\8.3.27.2130\bin"
```

Или просто без параметров (автопоиск по `1cestart.cfg`):

```powershell
.\Register-1CCom.cmd
```

**Из cmd, Проводника (двойной клик) или Run:**

```bat
cd /d "d:\старый ноут\Cursor\1c-analyst-tools"
Register-1CCom.cmd
```

**Из cmd одной строкой** (обязательно `powershell.exe` в начале):

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "d:\старый ноут\Cursor\1c-analyst-tools\Register-1CCom.ps1"
```

> Неверно в PowerShell: `-NoProfile -ExecutionPolicy Bypass -File ...` без `powershell.exe` — параметры не являются командой.  
> Регистрация `comcntr.dll` через regsvr32 **требует прав администратора Windows** (один раз на ПК).  
> Если у пользователя нет админ-прав — заявка в IT (текст заявки выводит `Register-1CCom.cmd`).  
> До регистрации COM доступны режимы **offline** и **research** (без live-запросов к ИБ).

### Без прав администратора Windows

| Ситуация | Что делать |
|----------|------------|
| COM уже зарегистрирован (при установке 1С IT) | Ничего — `onec_com_status` → `readyForConnect=true` |
| COM не зарегистрирован | Заявка в IT: `Register-1CCom.cmd` или `regsvr32` на `comcntr.dll` |
| Нельзя ждать IT | Агент в режиме **offline/research**: ИТС, форумы, кейсы, Obsidian |

Скрипт `Register-1CCom.cmd` при отсутствии прав выведет готовый текст заявки с путями к DLL.

**Диагностика COM:**

```powershell
.\scripts\Diagnose-OneCDataMcp.ps1
```

**Нет окна успеха / COM не регистрируется:**

1. Проверьте, что файл есть (путь из `1cestart.cfg`, не угадывайте версию):

```powershell
Select-String InstalledLocation "$env:APPDATA\1C\1CEStart\1cestart.cfg"
Test-Path "C:\Program Files\1cv8\8.3.27.1964\bin\comcntr.dll"
```

2. Если `Test-Path` = **False** — укажите реальный каталог `bin`:

```powershell
.\Register-1CCom.cmd -PlatformPath "C:\Program Files\1cv8\8.3.27.1964\bin"
```

3. Ручная регистрация (**только учётная запись администратора**, 64-bit `regsvr32`, **не** SysWOW64):

```bat
C:\Windows\System32\regsvr32.exe "C:\Program Files\1cv8\8.3.27.1964\bin\comcntr.dll"
```

4. Скрипт печатает статус **Before/After registration** для `V83.COMConnector` и `V85.COMConnector`. Для базы 8.5 нужен **V85**.

### 2. MCP-сервер

Уже создаётся установщиком. Вручную:

```powershell
.\scripts\Setup-Mcp.ps1
```

Учётные данные **1С:ИТС** — агент запрашивает сам через `question` и сохраняет через `onec_its_configure` (как `onec_connect` для базы). Файл `.onec-web.json` создаётся автоматически; вручную настраивать не нужно.

Опционально: env `ONEC_ITS_USER`, `ONEC_ITS_PASSWORD` или заранее заполненный `.onec-web.json` (см. example).

Если поиск падает с ошибкой SSL (корпоративный прокси): в `.onec-web.json` задайте `"verify_ssl": false` или `ONEC_WEB_VERIFY_SSL=false`.

В [`opencode.json`](opencode.json) при необходимости замените команду MCP:

```json
"command": ["mcp/.venv/Scripts/python.exe", "mcp/server.py"]
```

**Cursor:** в `.cursor/mcp.json` должен быть сервер `onec-data` (см. корень workspace).

**Для пользователя (один раз):** `scripts\Setup-Mcp.ps1`, `Register-1CCom.cmd` (UAC). Дальше MCP сам чинит BOM и сессию при старте; connect — только база + логин + пароль, без `platform_version`.

#### MCP пропал или connect обрывается по таймауту

1. **Settings → MCP → onec-data → Restart** (или Reload Window).
2. Проверка: `onec_ping` (без COM), затем **`onec_com_status`** (COM V83/V85 и `1cestart.cfg`).
3. Локально: `scripts\Diagnose-OneCDataMcp.ps1` или `scripts\Diagnose-OneCDataMcp.cmd`
4. **Connect:** `onec_connect` **без** `platform_version` и **без** `refresh_metadata=true` (по умолчанию).
5. Затем отдельно: `onec_refresh_metadata` (может занять 5–15 мин на первой базе 8.5).
6. **COM не зарегистрирован:** `Register-1CCom.cmd` (для баз 8.5 нужен **V85.COMConnector**). Подтвердите UAC. **Открывать 1С:Предприятие заранее не нужно** — достаточно COM.
7. Connect с **`info_base_path`**, не с «битым» именем из ibases.v8i
8. Первый COM-connect может занять **30–60 с** — это нормально, не объединяйте с выгрузкой метаданных.
9. Ошибка JSON `Expecting value` — обновите `Get-1CData.ps1` / перезапустите MCP
10. **ParserError** в PowerShell (кириллица / «неожиданный токен») — `.ps1` без UTF-8 BOM. Из каталога `1c-analyst-tools`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Fix-AllPs1Utf8Bom.ps1"
```

Или `scripts\Fix-AllPs1Utf8Bom.cmd`. Затем **Settings → MCP → onec-data → Restart**.

**Профилактика BOM:** в каталоге есть `.editorconfig` и `.vscode/settings.json` — Cursor сохраняет `.ps1` в UTF-8 BOM. Если правите скрипты вне Cursor — снова запустите Fix-скрипт.

### 3. Модели

В UI доступны **все** провайдеры OpenCode (встроенные, подключённые через `/connect`) плюс проектные:

| Провайдер | Модели / назначение |
|-----------|---------------------|
| **1bit AI** (`1bitai`) | `qwen3-coder` — **по умолчанию** для агента 1c-analyst; `qwen3.5-35b` — альтернатива |
| **Local LLM** (`local`) | Ollama / совместимый endpoint `http://127.0.0.1:11434/v1` |
| **OpenCode** и др. | встроенные и авторизованные провайдеры — выбор в списке моделей |

Прокси **1bitai** → `http://127.0.0.1:18765/v1` → `https://api.1bitai.ru`.

API-ключ (один раз):

```powershell
.\scripts\Set-1bitApiKey.ps1
```

Или вручную: переменная пользователя Windows `ONEBITAI_API_KEY`, либо `provider.1bitai.options.apiKey` в `opencode.local.json` (файл в `.gitignore`).

### 4. Запуск (основной сценарий — только OpenCode)

1. Запустите свою LLM (Ollama, vLLM, корпоративный gateway и т.п.).
2. Из каталога проекта:

```bat
cd /d "d:\старый ноут\Cursor\1c-analyst-tools"
.\Start-OpenCode.cmd
```

Скрипт: Bridge (если настроен) → прокси 1bit AI → **`opencode web`** (браузер, не консольный TUI). Используется `bin\opencode.exe` (1.16+).

При наличии `bridge/agent/bridge-agent.json` автоматически поднимается Bridge Agent для стабильного `onec_query`.

3. Агент **1c-analyst** выбран по умолчанию. Опишите проблему в чате.
4. Агент определит режим (**live** / **offline** / **research**) и при необходимости запросит базу или доступ к ИТС.

### 4a. Альтернатива: launcher

```bat
Start-1CAnalyst.cmd
```

Запросит базу, логин, пароль, описание проблемы, сохранит `.onec-session.json` и запустит OpenCode.

### 5. Smoke-тест (без OpenCode)

```powershell
.\scripts\Test-AnalystStack.ps1
```

## Компоненты

| Файл | Назначение |
|------|------------|
| [`Get-1CData.ps1`](Get-1CData.ps1) | CLI: запрос к базе, JSON/CSV |
| [`Register-1CCom.ps1`](Register-1CCom.ps1) | Регистрация COM |
| [`Install.cmd`](Install.cmd) | Установка стека одной командой (winget + MCP + OpenCode) |
| [`scripts/Install-1CAnalystStack.ps1`](scripts/Install-1CAnalystStack.ps1) | Логика установщика |
| [`Start-1CAnalyst.ps1`](Start-1CAnalyst.ps1) | Launcher: credentials + OpenCode |
| [`mcp/server.py`](mcp/server.py) | MCP: `onec_connect`, `onec_query`, метаданные, … |
| [`Lib/1CMetadataExport.ps1`](Lib/1CMetadataExport.ps1) | COM-выгрузка метаданных в `metadata/cache/` |
| [`Lib/1CConfigDump.ps1`](Lib/1CConfigDump.ps1) | Выгрузка конфигурации в XML (конфигуратор) |
| [`scripts/Dump-1CConfigToFiles.ps1`](scripts/Dump-1CConfigToFiles.ps1) | CLI: DumpConfigToFiles для анализа BSL |
| [`opencode.json`](opencode.json) | Конфиг OpenCode (MCP, agent, permissions) |
| [`.opencode/agents/1c-analyst.md`](.opencode/agents/1c-analyst.md) | Агент-аналитик |
| [`.opencode/skills/`](.opencode/skills/) | Skills: investigation, query-writing, connection, ut-patterns |
| [`AGENTS.md`](AGENTS.md) | Правила проекта для OpenCode |
| [`queries/`](queries/) | Шаблоны запросов |

## MCP-инструменты

| Tool | Описание |
|------|----------|
| `onec_welcome` | Приветствие: `formatted_user` + меню `question` (без MCP в чате); сброс подключения |
| `onec_connect` | Подключение к ИБ + **auto metadata** (COM → `metadata/cache/`) |
| `onec_check_connection` | Проверка подключения |
| `onec_list_infobases` | Список баз из ibases.v8i |
| `onec_metadata_status` | Статус кэша метаданных |
| `onec_metadata_search` | Поиск объектов по имени/синониму |
| `onec_metadata_object` | Карточка объекта (реквизиты, ТЧ, измерения) |
| `onec_refresh_metadata` | Принудительное обновление кэша |
| `onec_query` | Read-only запрос, JSON (max 5000 строк) |
| `onec_config_sources_register` | Регистрация каталога XML-исходников (спросить путь у пользователя) |
| `onec_dump_config` | Выгрузка конфигурации в файлы (partial/full, нужен connect) |
| `onec_config_read_module` | Чтение BSL из зарегистрированных XML |
| `onec_config_search_code` | Поиск по BSL в XML-исходниках |
| `onec_read_module` | Запасной: модуль через конфигуратор (COM не читает код) |
| `onec_web_research_status` | Статус ИТС; `agent_action` если нужен логин |
| `onec_its_configure` | Логин/пароль ИТС от пользователя + проверка |
| `onec_its_disconnect` | Сброс учётных данных ИТС |
| `onec_its_search` | Поиск в документации 1С:ИТС |
| `onec_its_fetch` | Загрузка текста статьи ИТС |
| `onec_web_search_forums` | Поиск по форумам (Infostart, Mista, …) |
| `onec_search_cases` | Поиск кейсов (JSON + Obsidian) |
| `onec_get_case` | Кейс по id |
| `onec_save_case` | Сохранить/дополнить кейс (draft при приближении к решению, final в конце) |
| `onec_investigation_status` | Активный `case_id`, пути к заметкам Cases/Sessions |
| `onec_obsidian_status` | Путь vault и список баз |
| `onec_obsidian_set_context` | Имя папки ИБ без connect |
| `onec_obsidian_save_requirements` | Лист требований в Requirements/ |
| `onec_obsidian_save_session` | Заметка сессии (вместе с draft-кейсом) |
| `onec_obsidian_append_session` | Дополнение заметки при уточнениях пользователя |
| `onec_obsidian_prepare_requirements` | Контекст перед ЛТ (кейсы, справочники) |
| `onec_obsidian_search_handbooks` | Поиск в справочниках конфигурации |

Подключение через env (устанавливает launcher):

- `ONEC_IB_PATH` или `ONEC_SERVER` + `ONEC_REF`
- `ONEC_USER`, `ONEC_PASSWORD`

## Get-1CData.ps1

```powershell
# Прямой запрос
.\Get-1CData.ps1 `
  -InfoBasePath "C:\Users\aaposmetev\Documents\1C\DemoTrd" `
  -User "Администратор" `
  -QueryFile ".\queries\customer_orders.txt" `
  -AgentMode

# Режим AgentMode: ReadOnly, MaxRows=500, без лишнего вывода
```

Параметры: `-ReadOnly`, `-AgentMode`, `-MaxRows`, `-Quiet`, `-ListInfoBases -OutputFormat Json`.

## OpenCode: agent и skills

- Agent: **1c-analyst** — live / offline / research (skill `1c-work-modes`)
- Skills: `1c-investigation-pipeline`, `1c-requirements-sheet`, `1c-investigation`, `1c-query-writing`, `1c-connection`, `1c-ut-patterns`, `1c-cases`, `1c-web-research`, `1c-work-modes`
- Шаблон ЛТ: `templates/Лист_требований.md`

Права в `opencode.json`: edit/bash запрещены, MCP и skills разрешены.

## Тестовый сценарий (DemoTrd)

1. `.\scripts\Test-AnalystStack.ps1`
2. `.\Start-1CAnalyst.ps1 -InfoBasePath "C:\Users\aaposmetev\Documents\1C\DemoTrd" -User "Администратор" -Password "" -Problem "Почему заказ ТД00-000007 не отгружен полностью?"`
3. В OpenCode agent `1c-analyst` выполняет `onec_check_connection` → `onec_query` по заказу и реализациям

## Безопасность

- Пароли не коммитить (`session-prompt.md`, `opencode.local.json` в `.gitignore`)
- Только read-only запросы
- Лимит строк в MCP и `-AgentMode`

## Ограничения

- Имена метаданных зависят от конфигурации (УТ/ERP/БП)
- Локальная модель должна поддерживать tool calling
- COM и платформа 1С — только Windows
