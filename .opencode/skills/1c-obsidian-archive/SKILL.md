---
name: 1c-obsidian-archive
description: Сохранение артефактов аналитика в Obsidian — кейсы, листы требований, история сессий по проекту и конфигурации
---

# Архив в Obsidian

Канон vault: **`1c-analyst-tools/Obsidian/`** (создаётся автоматически) или `ONEC_OBSIDIAN_VAULT`.

Структура — **одна папка на конфигурацию** (не на ИБ):

```
1c-analyst-tools/Obsidian/{Конфигурация}/
  Cases/
  Requirements/
  Sessions/
  Справочники/
```

`{Конфигурация}` — каноническое имя (например «БИТ Управление медицинским центром»). Варианты вроде «БИТ-УМЦ (демо)», «БИТ_Айболит» схлопываются в одну папку по алиасам конфигурации. Без connect: `offline` или `ONEC_OBSIDIAN_DATABASE`.

Имя файла: `ГГГГ-ММ-ДД_ТипДокумента_Название.md` (русский язык).

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
| Лист требований | `onec_obsidian_save_requirements` | После фазы A и B — **обновление того же файла** в сессии (не новые версии) + JSON-кейс |
| Заметка сессии | `onec_obsidian_save_session` | Вместе с draft-кейсом: резюме + диалог |
| Дополнение сессии | `onec_obsidian_append_session` | Уточнения пользователя в ту же заметку Sessions |

## onec_obsidian_save_requirements

- `body_markdown` — полный текст ЛТ по шаблону (§1–7, включая §2.1 ценность, §4.1–4.4, таблицу трудочасов).
- `title` — заголовок задачи.
- `phase`: `draft` | `final` — обновляет **текущий** ЛТ сессии, не создаёт черновики-файлы.
- `keywords` — через запятую; оформляются как `[[wiki-ссылки]]` в тексте и в §Связи.
- `objects_used` — объекты метаданных через `;` (авто-wikilink в тексте).
- Frontmatter: `configurationName` (полное название), `configurationVersion`, `vaultFolder`.
- Параллельно сохраняется JSON-кейс: `Requirements/...json` (поле `json_relative_path` в ответе).
- Связи: с заметкой Sessions и объектами метаданных в разделе `## Связи`.

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
