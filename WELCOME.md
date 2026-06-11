# Новая сессия — приветствие

MCP-сервер `onec-data` → инструменты с префиксом `onec-data_` (см. `AGENTS.md`).

При **первом ответе** в новой сессии (или по «привет», `/welcome`, `/start`):

1. **Один раз** `onec-data_onec_welcome(first_user_message=<текст>)` — до других инструментов. Повторный вызов не нужен.
2. Покажите пользователю текст ответа `onec-data_onec_welcome` **как есть** (без JSON и списка MCP).
3. **В том же ответе** вызовите **`question`** с вариантами из поля `question` ответа welcome:
   - `title` → заголовок формы
   - `prompt` → пояснение
   - `options` → варианты `{id, label}`

**Не дублируйте** варианты текстом в чате — выбор только через окно question.

4. После выбора в question — **`onec-data_onec_set_task_type(task_id=...)`** (id: investigation, requirements, …). **Не** `onec-data_onec_declare_symptom` с текстом кнопки.
5. Спросите пользователя **текстом**: что за ошибка, что делали, какой документ → **`onec-data_onec_declare_symptom(symptom=...)`** только с этим ответом.
6. Skill по `user_menu[].hint`; при необходимости доступ к ИБ.

**До question запрещены:** `onec-data_onec_search_cases`, `onec-data_onec_save_case`, `onec-data_onec_connect`.  
**В чат не вставлять:** сырой JSON. Инструменты connect/welcome/cases возвращают готовый текст.

Поле `formatted` и `capabilities` — **только для агента**, не показывать пользователю.

## Варианты меню (question)

| id | Смысл |
|----|--------|
| `investigation` | Ошибка / расхождение в учёте |
| `requirements` | Лист требований |
| `mechanism` | Как устроен механизм |
| `research` | Общий вопрос по платформе |
| `continue` | Задача уже в первом сообщении |

Даже если пользователь сразу описал задачу — сначала краткое приветствие + **question** (вариант «Уже описал задачу»).
