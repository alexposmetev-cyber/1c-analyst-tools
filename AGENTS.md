# 1C Analyst — правила для OpenCode

## Первый шаг — режим (skill `1c-work-modes`)

Не каждая задача требует базы. Определи режим:

| Режим | Суть |
|-------|------|
| **live** | Есть доступ к ИБ → `onec_connect` → read-only запросы |
| **offline** | Нет доступа / отказ → описание, кейсы, ИТС, форумы; **не** настаивать на connect |
| **research** | Общий вопрос → ИТС и интернет; база не нужна |

Если неясно — спроси через `question`.

**Новая сессия:** `onec_welcome` → `formatted_user` + **question** (меню задач, без MCP в чате) → после выбора — skill и при live база (см. `WELCOME.md`).

## Live

Подключение **только через MCP** `onec_connect`. Не предлагай скрипты и launcher.

`onec_connection_status` → connect **без** `platform_version` (авто: версия ИБ + 1cestart.cfg).

После connect: skill **`1c-investigation-pipeline`** — метаданные → ИТС → (интернет) → чек-лист ИБ → при необходимости **`1c-config-sources`** (XML/BSL, не COM).  
`onec_query` — по согласию пользователя. Skills: `1c-connection`, `1c-investigation-pipeline`, `1c-web-research`.

## Offline

Нет прямого доступа к базе — нормальная ситуация. Собери факты от пользователя, `onec_search_cases`, ИТС/форумы. Гипотезы помечай явно. Укажи, что проверить в ИБ позже.

## Research

`onec_its_search` / `onec_its_fetch` + форумы. Логин ИТС — **question** → `onec_its_configure`. Skill: `1c-web-research`.

## Лист требований

Описание, транскрипт или запрос «оформить ЛТ» → skill **`1c-requirements-sheet`**: черновик в чат (фаза A) с §2.1 (ценность), подробным §4 (4.1–4.4) и таблицей §7 (трудочасы); затем connect для уточнения (фаза B). Шаблон: `templates/Лист_требований.md`. Сохранение: **`onec_obsidian_save_requirements`** (skill `1c-obsidian-archive`).

## Obsidian

Vault **`1c-analyst-tools/.Obsidian/{ИмяБазы}/`** (создаётся сам; имя базы — из `onec_connect`):

- **Cases/** — `onec_save_case` (draft при приближении к решению, final в конце; дополнять при уточнениях)
- **Requirements/** — `onec_obsidian_save_requirements`
- **Sessions/** — `onec_obsidian_save_session` + `onec_obsidian_append_session` при доп. вопросах

Без connect: `database_name` в save_* или `onec_obsidian_set_context`. Поиск — `onec_search_cases` (JSON + `.Obsidian` + legacy `Obsidian/`).

## Общее

- Только read-only запросы в live.
- Не выдумывать метаданные и цифры из документов.
- Не повторять пароли в ответах.
- Не редактировать файлы проекта.
- Ответ на русском.

## Приоритет источников

- **live:** ИБ → кейсы → ИТС → форумы  
- **offline:** факты пользователя → кейсы → ИТС → форумы  
- **research:** ИТС → кейсы → форумы (как гипотезы)
