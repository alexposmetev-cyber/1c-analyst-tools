---
name: 1c-connection
description: Подключение к базе 1С через MCP — только в режиме live, когда у пользователя есть доступ
---

# Подключение к базе 1С

## Когда подключаться

Только **live** (skill `1c-work-modes`), когда есть база, логин и пароль на этой машине.

**Не подключайся** в offline/research или после отказа пользователя.

## Единственный способ для агента

Только MCP. Скрипты пользователю **не предлагать**.

## Bridge Agent (рекомендуется для onec-data_onec_query)

Долгоживущий COM-мост: стабильнее многократных `onec-data_onec_query` через Get-1CData.ps1.

**Пользователь (один раз):**

1. `bridge\agent\bridge-agent.json` — копия из `bridge-agent.json.example`, та же ИБ что в `onec-data_onec_connect`
2. `Start-OpenCode.cmd` — автоматически поднимает оркестратор и Bridge Agent, затем OpenCode

Вручную (отладка): `bridge\Start-Orchestrator.cmd` + `bridge\Start-BridgeAgent.cmd`

**Агент:** `onec-data_onec_bridge_status` после connect — `readyForQuery: true` → `onec-data_onec_query` автоматически через Bridge (`via: bridge` в ответе).

Если Bridge не запущен — `onec-data_onec_query` идёт через COM с полем `bridgeNote` в ответе.

### Алгоритм

1. В начале чата: `onec-data_onec_welcome(first_user_message=…)` — **всегда** сбрасывает сохранённое подключение (новая чат-сессия).
2. `onec-data_onec_connection_status` — подтвердить, что сессия пуста.
3. `onec-data_onec_list_infobases` → **question** по очереди: база → пользователь 1С → **пароль** (отдельный вопрос, даже если пустой).
4. При смене базы — `onec-data_onec_disconnect` → новый connect.
5. **`onec-data_onec_confirm_credentials(..., password_acknowledged=true)`** — только после явного ответа про пароль.
6. **`onec-data_onec_connect(...)`** — те же user, база и password, что в confirm_credentials.

   **Не передавайте `platform_version`** — версия платформы подбирается автоматически:
   - по файлу ИБ / реестру `ibases.v8i` (Version=);
   - каталог установки из **`1cestart.cfg`** (InstalledLocation);
   - зарегистрированный COM нужной линейки (8.3 / 8.5).

   ```json
   {"user": "Администратор", "info_base_name": "1", "password": ""}
   ```

   или

   ```json
   {"user": "Администратор", "info_base_path": "C:\\Users\\...\\DemoTrd", "password": ""}
   ```

7. Ответ connect — русский текст. Дождитесь **конкретного** описания задачи → **`onec-data_onec_declare_symptom`** (не «Ошибка в учёте»).
8. Без конкретного `declare_symptom` MCP **заблокирует** `its_search`, `search_cases`, `metadata_search`.
9. **`onec-data_onec_refresh_metadata`** — после declare_symptom, отдельным вызовом.
10. Далее — расследование по skill pipeline; **не** подставлять текст из найденных кейсов в ИТС.

**Не передавайте** `refresh_metadata=true` в `onec-data_onec_connect` без необходимости — клиент MCP оборвёт по таймауту.

### Ошибка «COMConnector 8.3 не может работать с базой 8.5»

ИБ на **8.5**, а подключение идёт через **V83.COMConnector**.

**Агенту:** `onec-data_onec_connect` с **`info_base_path`** (полный каталог, не битое имя из реестра), **без** `platform_version`. Скрипт сам переключится на 8.5 после текста ошибки.

**Пользователю:** `Register-1CCom.cmd` — регистрация COM **8.3 и 8.5**. Без V85.COMConnector подключение к базе 8.5 невозможно.

### «Expecting value» / «не JSON», но в логе есть `Connected: 1`

COM подключился, но MCP не распарсил stdout: предупреждения PowerShell о `-PlatformPath` или многострочный JSON. Исправлено в AgentMode (тихие warning, одна строка JSON, устойчивый парсер). **Перезапустите MCP** и повторите `onec-data_onec_connect` — иначе `connected` в статусе останется false.

### «Expecting value: line 1 column 1» (пустой JSON)

Ошибка COM без JSON в stdout. Сейчас в AgentMode: `{"status":"error","message":"..."}`.

### Смена базы / конфигурации

После `onec-data_onec_disconnect` + connect к другой ИБ:

- другой каталог `.Obsidian/{ИмяБазы}/`;
- другой кэш метаданных;
- **не смешивать** объекты и кейсы предыдущей конфигурации (см. `1c-requirements-sheet`).

### Метаданные

| Инструмент | Назначение |
|------------|------------|
| `onec-data_onec_metadata_status` | Готовность кэша |
| `onec-data_onec_metadata_search` | Поиск объектов |
| `onec-data_onec_metadata_object` | Карточка объекта |
| `onec-data_onec_refresh_metadata` | Обновить кэш |

## MCP onec-data пропал из сессии

1. **Cursor:** Settings → MCP → `onec-data` → **Restart** (или Reload Window).
2. Проверка: `onec-data_onec_ping` — должен ответить за секунду.
3. Перед connect: **`onec-data_onec_com_status`** — V83/V85 и `1cestart.cfg`.
4. Локально: `scripts\Diagnose-OneCDataMcp.ps1`
5. Если connect обрывался по таймауту — **не** объединяйте connect и выгрузку метаданных; `platform_version` не нужен. Первый COM-connect может занять 30–60 с.

### COM не зарегистрирован / таймаут connect

| Симптом | Действие пользователю |
|---------|----------------------|
| `onec-data_onec_com_status`: V83/V85 = false | **Права админа Windows** (один раз на ПК): IT выполняет **`Register-1CCom.cmd`** или `regsvr32` на `comcntr.dll`. Пользователь без админа — заявка в IT, режим offline/research |
| База 8.5, только V83 | `Register-1CCom.cmd` (нужен V85.COMConnector) |
| Таймаут без ошибки COM | Повторить `onec-data_onec_connect`; не передавать `refresh_metadata=true` |
| `InstalledLocation` пуст | Запустить 1С один раз **или** `-PlatformPath` в Register-1CCom |

**Не требуется:** открывать 1С:Предприятие/Конфигуратор перед connect.

**Требуется для первой регистрации COM:** права администратора Windows (обычно IT). Без админа пользователь сам regsvr32 не выполнит.

## Типичные ошибки

| Симптом | Действие |
|---------|----------|
| invalid connection parameters | Только `user`, `info_base_name` / `info_base_path`, `password` |
| Timeout connect | `onec-data_onec_com_status`; Register-1CCom.cmd; повторить без refresh_metadata; первый connect 30–60 с |
| `File=` в info_base_path | Использовать `info_base_name` или чистый каталог |

## Безопасность

Пароль не повторять в ответах. Не писать credentials в репозиторий.
