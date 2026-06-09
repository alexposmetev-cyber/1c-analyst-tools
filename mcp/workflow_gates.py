"""Фазы сессии аналитика — блокировка connect/расследования без учётных данных и симптома."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKFLOW_FILENAME = ".onec-workflow.json"
MIN_SYMPTOM_LENGTH = 25

GENERIC_SYMPTOM_PHRASES = (
    "ошибка в учёте",
    "ошибка в учете",
    "ошибка учёта",
    "ошибка учета",
    "не работает",
    "не сходится",
    "расхождение",
    "помогите",
    "разберись",
    "есть ошибка",
    "ошибка в базе",
    "проблема в учёте",
    "проблема в учете",
)

TASK_TYPE_IDS = frozenset(
    {"investigation", "requirements", "mechanism", "research", "continue"}
)

MENU_BUTTON_MESSAGE = (
    "Это похоже на выбор кнопки в меню «Чем помочь?», а не описание задачи. "
    "Вызовите onec_set_task_type после question, затем спросите пользователя: "
    "точный текст ошибки, что делали, какой документ или операция — и только потом onec_declare_symptom."
)

AGENT_NARRATION_PREFIXES = (
    "пользователь не может",
    "пользователь не смог",
    "пользователь столкнулся",
    "пользователь пытается",
    "пользователь описал",
    "пользователь выбрал",
    "у пользователя",
    "клиент сообщил",
    "клиент не может",
    "пользователь сообщил",
)

AGENT_NARRATION_MARKERS = (
    "не указал конкретн",
    "не указала конкретн",
    "общую задачу",
    "общая задача",
    "не предоставил",
    "не сообщил детал",
    "не уточнил",
    "без конкретики",
    "без деталей",
    "выбрал в меню",
    "нажал кнопку",
)

ASK_USER_VIA_QUESTION = (
    "СТОП: не вызывайте onec_declare_symptom снова. "
    "Один раз задайте вопрос пользователю через question: "
    "«Опишите ошибку — точный текст, документ, что делали». "
    "После ответа в чат — declare_symptom с текстом пользователя."
)

CASE_DERIVED_MARKERS = (
    "оформление счетов-фактур",
    "оформление счетов фактур",
    "таможенных документов",
    "требуетсяоформлениесчетафактуры",
    "закрытие месяца",
    "закрытии месяца",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _workflow_path(root: Path) -> Path:
    return root / WORKFLOW_FILENAME


def load_workflow(root: Path) -> dict[str, Any]:
    path = _workflow_path(root)
    if not path.is_file():
        return _default_workflow()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_workflow()
    if not isinstance(data, dict):
        return _default_workflow()
    merged = _default_workflow()
    merged.update(data)
    return merged


def _default_workflow() -> dict[str, Any]:
    return {
        "welcomeDone": False,
        "welcomeShownAt": "",
        "credentialsConfirmed": False,
        "credentialsUser": "",
        "credentialsBase": "",
        "passwordAsked": False,
        "passwordAcknowledged": False,
        "taskType": "",
        "taskTypeLabel": "",
        "symptom": "",
        "symptomDeclared": False,
        "symptomRejectCount": 0,
        "connectedAt": "",
        "updatedAt": "",
    }


def save_workflow(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data["updatedAt"] = _now_iso()
    _workflow_path(root).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data


def clear_workflow(root: Path) -> None:
    path = _workflow_path(root)
    if path.is_file():
        path.unlink()


def reset_workflow(root: Path) -> dict[str, Any]:
    return save_workflow(root, _default_workflow())


def mark_welcome_done(root: Path) -> dict[str, Any]:
    payload = load_workflow(root)
    payload["welcomeDone"] = True
    payload["welcomeShownAt"] = _now_iso()
    return save_workflow(root, payload)


def welcome_already_shown(root: Path) -> bool:
    workflow = load_workflow(root)
    return bool(workflow.get("welcomeShownAt"))


def mark_credentials_confirmed(
    root: Path,
    *,
    user: str,
    info_base: str,
    password_acknowledged: bool = False,
) -> dict[str, Any]:
    payload = load_workflow(root)
    payload["credentialsConfirmed"] = True
    payload["credentialsUser"] = user.strip()
    payload["credentialsBase"] = info_base.strip()
    payload["passwordAcknowledged"] = password_acknowledged
    payload["passwordAsked"] = password_acknowledged
    return save_workflow(root, payload)


def credentials_password_gate_message(root: Path, *, password_acknowledged: bool) -> str | None:
    if password_acknowledged:
        return None
    workflow = load_workflow(root)
    if workflow.get("passwordAcknowledged"):
        return None
    return (
        "Пароль для входа в 1С ещё не подтверждён. Спросите через question: "
        "«Пароль пользователя 1С?» (можно пустой, если без пароля). "
        "Затем onec_confirm_credentials(..., password=..., password_acknowledged=true)."
    )


def _question_menu_entries() -> list[tuple[str, str]]:
    from welcome import _user_task_menu

    return [(item["id"], item["label"]) for item in _user_task_menu()]


def is_question_menu_selection(text: str) -> bool:
    lowered = text.lower().strip().rstrip(".!")
    if not lowered:
        return False
    if lowered in TASK_TYPE_IDS:
        return True

    for task_id, label in _question_menu_entries():
        label_lower = label.lower()
        if lowered == label_lower or lowered == task_id:
            return True
        if len(lowered) <= 40 and (lowered in label_lower or label_lower in lowered):
            return True

    for phrase in GENERIC_SYMPTOM_PHRASES:
        if lowered == phrase or lowered.rstrip(".!") == phrase:
            return True

    return False


def mark_task_type(root: Path, task_id: str, label: str = "") -> dict[str, Any]:
    task_id = task_id.strip().lower()
    if task_id not in TASK_TYPE_IDS:
        raise ValueError(
            f"task_id должен быть один из: {', '.join(sorted(TASK_TYPE_IDS))}"
        )

    payload = load_workflow(root)
    payload["taskType"] = task_id
    payload["taskTypeLabel"] = (label or "").strip()
    if not payload["taskTypeLabel"]:
        for menu_id, menu_label in _question_menu_entries():
            if menu_id == task_id:
                payload["taskTypeLabel"] = menu_label
                break
    payload["symptom"] = ""
    payload["symptomDeclared"] = False
    return save_workflow(root, payload)


def task_type_followup_message(root: Path) -> str:
    workflow = load_workflow(root)
    label = str(workflow.get("taskTypeLabel") or workflow.get("taskType") or "").strip()
    if workflow.get("taskType") == "investigation":
        return (
            f"Тип задачи зафиксирован: {label or 'расследование ошибки'}.\n\n"
            "Следующий шаг — один вызов question: «Опишите ошибку: точный текст сообщения, "
            "документ, что делали».\n\n"
            "Запрещено вызывать onec_declare_symptom, пока пользователь не ответил текстом в чат."
        )
    if workflow.get("taskType") == "requirements":
        return (
            f"Тип задачи: {label or 'лист требований'}. "
            "Спросите описание доработки или приложите транскрипт."
        )
    if workflow.get("taskType") == "continue":
        return (
            "Продолжаем с задачей из сообщения пользователя. "
            "Если описание короткое — уточните детали, затем onec_declare_symptom."
        )
    return (
        f"Тип задачи: {label or workflow.get('taskType', '')}. "
        "Уточните запрос пользователя, затем onec_declare_symptom при необходимости."
    )


def _agent_narration_error() -> str:
    return ASK_USER_VIA_QUESTION


def validate_symptom(symptom: str) -> tuple[bool, str]:
    text = symptom.strip()
    if is_question_menu_selection(text):
        return False, MENU_BUTTON_MESSAGE

    lowered = text.lower()
    for prefix in AGENT_NARRATION_PREFIXES:
        if lowered.startswith(prefix):
            return False, _agent_narration_error()

    for marker in AGENT_NARRATION_MARKERS:
        if marker in lowered:
            return False, _agent_narration_error()

    if len(text) < MIN_SYMPTOM_LENGTH:
        return (
            False,
            f"Симптом слишком короткий (минимум {MIN_SYMPTOM_LENGTH} символов). "
            "Попросите текст ошибки, что делали, какой документ или операция.",
        )

    for phrase in GENERIC_SYMPTOM_PHRASES:
        if lowered == phrase or lowered.rstrip(".!") == phrase:
            return (
                False,
                f"Симптом «{text}» слишком общий. Нужны детали: точный текст ошибки, "
                "документ, операция (закрытие месяца, проведение и т.д.).",
            )

    return True, ""


def record_symptom_rejection(root: Path) -> int:
    payload = load_workflow(root)
    count = int(payload.get("symptomRejectCount") or 0) + 1
    payload["symptomRejectCount"] = count
    save_workflow(root, payload)
    return count


def mark_symptom(root: Path, symptom: str) -> dict[str, Any]:
    text = symptom.strip()
    ok, _ = validate_symptom(text)
    payload = load_workflow(root)
    payload["symptom"] = text[:500]
    payload["symptomDeclared"] = ok
    if ok:
        payload["symptomRejectCount"] = 0
    return save_workflow(root, payload)


def declared_symptom(root: Path) -> str:
    return str(load_workflow(root).get("symptom") or "").strip()


def validate_investigation_query(symptom: str, query: str) -> tuple[bool, str]:
    """Запрос к ИТС/метаданным не должен содержать детали из чужого кейса, которых нет в симптоме."""
    symptom_text = symptom.strip().lower()
    query_text = query.strip().lower()
    if not symptom_text or not query_text:
        return False, "Пустой симптом или запрос."

    for marker in CASE_DERIVED_MARKERS:
        if marker in query_text and marker not in symptom_text:
            return (
                False,
                f"Запрос содержит «{marker}», которого нет в симптоме пользователя. "
                "Ищите только по зафиксированному симптому, не подставляйте текст из найденных кейсов.",
            )

    return True, ""


def mark_connected(root: Path) -> dict[str, Any]:
    payload = load_workflow(root)
    payload["connectedAt"] = _now_iso()
    return save_workflow(root, payload)


def maybe_symptom_from_first_message(root: Path, first_user_message: str) -> dict[str, Any]:
    """Вариант «уже описал задачу» — симптом из первого сообщения, если он конкретный."""
    text = (first_user_message or "").strip()
    ok, _ = validate_symptom(text)
    if ok:
        return mark_symptom(root, text)
    return load_workflow(root)


def credentials_gate_message(root: Path) -> str | None:
    workflow = load_workflow(root)
    if workflow.get("credentialsConfirmed"):
        return None

    if not workflow.get("welcomeDone"):
        return (
            "Сначала вызовите onec_welcome и покажите меню question. "
            "Затем спросите базу, пользователя 1С и пароль."
        )

    return (
        "Перед подключением задайте пользователю вопрос через question:\n"
        "1) какая база (из onec_list_infobases);\n"
        "2) пользователь 1С (не логин Windows);\n"
        "3) пароль (можно пустой, если пользователь так указал).\n\n"
        "После ответа вызовите onec_confirm_credentials(user=..., info_base_name=..., password=...), "
        "затем onec_connect с теми же параметрами."
    )


def symptom_gate_message(root: Path) -> str | None:
    workflow = load_workflow(root)
    symptom = str(workflow.get("symptom") or "").strip()
    if workflow.get("symptomDeclared"):
        ok, _ = validate_symptom(symptom)
        if ok:
            return None

    task_label = str(workflow.get("taskTypeLabel") or "").strip()
    if workflow.get("taskType") and not symptom:
        prefix = f"В меню выбрано: «{task_label}» — это тип задачи, не описание ошибки. "
    else:
        prefix = ""

    return (
        prefix
        + "Спросите пользователя: «Опишите ошибку или задачу текстом» "
        f"(точный текст ошибки, документ, операция) и вызовите onec_declare_symptom(symptom=...) — "
        f"минимум {MIN_SYMPTOM_LENGTH} символов. "
        "Текст кнопки question (например «Ошибка в учёте») в declare_symptom передавать нельзя. "
        "Без этого нельзя искать в кейсах, ИТС и метаданных."
    )


def live_gate_message(root: Path, *, connection_verified: bool) -> str | None:
    symptom_block = symptom_gate_message(root)
    if symptom_block:
        return symptom_block

    if not connection_verified:
        return (
            "Нет подтверждённого подключения к базе. "
            "onec_list_infobases → question (база, пользователь, пароль) → "
            "onec_confirm_credentials → onec_connect."
        )

    return None


def investigation_gate_message(root: Path) -> str | None:
    """Кейсы, ИТС, форумы — нужен симптом (база не обязательна)."""
    return symptom_gate_message(root)
