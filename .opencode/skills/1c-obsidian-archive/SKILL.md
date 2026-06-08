---
name: 1c-obsidian-archive
description: Сохранение артефактов аналитика в Obsidian — кейсы, листы требований, история сессий по проекту и конфигурации
---

# Архив в Obsidian

Канон vault: **`1c-analyst-tools/Obsidian/`** (создаётся автоматически) или `ONEC_OBSIDIAN_VAULT`.

Структура — **одна папка на информационную базу**:

```
1c-analyst-tools/Obsidian/{ИмяБазы}/
  Cases/
  Requirements/
  Sessions/
  Справочники/
```

`{ИмяБазы}` — из `onec_connect` (имя в реестре ibases / каталог файловой ИБ / server_ref). Без connect: `offline` или `ONEC_OBSIDIAN_DATABASE`.

## Контекст пути

1. После **`onec_connect`** папка базы подставляется сама.
2. Без connect — `onec_obsidian_set_context(database_name="...")` или параметр `database_name` в save_*.
3. `onec_obsidian_status` — текущая папка и список баз в vault.

Конфигурация (`configuration_name`) — в frontmatter заметок, не в пути каталогов.

Старый каталог `Obsidian/` по-прежнему участвует в **поиске** кейсов.

## Что сохранять и когда

| Артефакт | Инструмент | Когда |
|----------|------------|--------|
| Кейс (draft/final) | `onec_save_case` | При приближении к решению (draft) и при финале (final); Obsidian + JSON |
| Дополнение кейса | `onec_save_case(case_id=...)` | Новые вопросы, гипотезы, методы — в тот же файл |
| Лист требований | `onec_obsidian_save_requirements` | После фазы A (черновик с §2.1, §4, §7) и после фазы B (уточнённые §4 и §7) |
| Заметка сессии | `onec_obsidian_save_session` | Вместе с draft-кейсом: резюме + диалог |
| Дополнение сессии | `onec_obsidian_append_session` | Уточнения пользователя в ту же заметку Sessions |

## onec_obsidian_save_requirements

- `body_markdown` — полный текст ЛТ по шаблону (§1–7, включая §2.1 ценность, §4.1–4.4, таблицу трудочасов).
- `title` — заголовок задачи.
- `phase`: `draft` | `final`.
- При необходимости: `database_name`, `configuration_name`.

После сохранения сообщи пользователю `relative_path` из ответа MCP.

## onec_obsidian_save_session

- `summary` — 5–15 предложений: задача, режим (live/offline), итог, открытые вопросы.
- `transcript_markdown` — опционально: хронология «Пользователь / Аналитик» или список ключевых решений.
- `mode`: `live` | `offline` | `research`.

## Поиск кейсов

`onec_search_cases` ищет JSON в `cases/` и markdown в `.Obsidian/**/Cases/` (и legacy `Obsidian/`).

## Запрещено

- Писать в vault в обход MCP (агент read-only).
- Сохранять пароли и персональные данные в Sessions/Requirements.

## Связь

- `1c-cases` — кейсы
- `1c-requirements-sheet` — ЛТ
- `1c-work-modes` — режим в summary сессии
