"""Тексты replyToUser для ответов MCP — только их показывать пользователю."""

from __future__ import annotations

import json
from typing import Any


CONNECT_FOLLOWUP = "Опишите задачу или симптом — с чем помочь?"

WELCOME_QUESTION_FOLLOWUP = (
    "Сейчас один раз откройте форму question: заголовок «Чем помочь?», "
    "варианты — investigation, requirements, mechanism, research, continue (см. WELCOME.md)."
)

WELCOME_ALREADY_SHOWN = (
    "Приветствие в этой сессии уже было. Не вызывайте onec-data_onec_welcome повторно — "
    "сразу question (title: «Чем помочь?») или ответьте пользователю коротко."
)

AGENT_ACTION_NO_JSON = (
    "AGENT_ACTION: ответ инструмента — готовый текст для пользователя. "
    "Передайте его как есть, без JSON и без служебных полей."
)


def plain_user_reply(text: str, followup: str = "") -> str:
    """Только русский текст — без JSON. Модель не должна иметь что копировать кроме этого."""
    lines = [text.strip()]
    if followup.strip():
        lines.extend(["", followup.strip()])
    return "\n".join(lines)


def wrap_agent_response(reply_to_user: str, **fields: Any) -> dict[str, Any]:
    """Словарь ответа: replyToUser первым, затем служебные поля."""
    payload: dict[str, Any] = {"replyToUser": reply_to_user.strip()}
    for key, value in fields.items():
        if value is not None and value != "" and value != [] and value != {}:
            payload[key] = value
    if "agent_action" not in payload:
        payload["agent_action"] = AGENT_ACTION_NO_JSON
    return payload


def dumps_agent_response(reply_to_user: str, **fields: Any) -> str:
    return json.dumps(wrap_agent_response(reply_to_user, **fields), ensure_ascii=False, indent=2)


def format_cases_reply(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return "Похожих кейсов в библиотеке не найдено."

    lines: list[str] = []
    for index, item in enumerate(summaries, start=1):
        symptom = str(item.get("symptom") or "без описания").strip()
        config = str(item.get("configurationName") or "").strip()
        preview = str(item.get("solutionPreview") or "").strip()
        warning = str(item.get("warning") or "").strip()

        line = f"{index}. {symptom}"
        if config:
            line += f" ({config})"
        if preview:
            line += f" — {preview}"
        if warning:
            line += f" [{warning}]"
        lines.append(line)

    text = "Похожие кейсы:\n" + "\n".join(lines)
    text += (
        "\n\nВажно: текст кейса — только ориентир. Для ИТС и метаданных используйте "
        "симптом пользователя из onec-data_onec_declare_symptom, не подставляйте ошибку из кейса без подтверждения."
    )
    return text


def format_connect_reply(payload: dict[str, Any]) -> str:
    connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    target = (
        str(connection.get("display_name") or connection.get("target") or "база").strip()
    )
    user = str(connection.get("user") or "").strip()
    config = str(metadata.get("configurationName") or "не определена").strip()
    version = str(metadata.get("version") or "").strip()
    meta_ready = bool(metadata.get("ready"))

    parts = [f"Подключено к базе «{target}»"]
    if user:
        parts.append(f"пользователь {user}")
    parts.append(f"конфигурация {config}")
    if version and version != "unknown":
        parts.append(f"версия {version}")
    parts.append("метаданные готовы" if meta_ready else "метаданные нужно обновить")

    via = str(payload.get("via") or "").strip()
    if via == "bridge":
        parts.append("запросы через Bridge")

    return ". ".join(parts) + "."


def format_connection_status_reply(payload: dict[str, Any]) -> str:
    if not payload.get("session_saved"):
        return (
            "К базе не подключены. Для live-режима укажите базу, пользователя и пароль — "
            "подключу через onec-data_onec_connect."
        )

    if payload.get("connected"):
        connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else payload
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        target = str(connection.get("target") or connection.get("display_name") or "база").strip()
        config = str(metadata.get("configurationName") or "").strip()
        text = f"Сессия активна: «{target}»"
        if config:
            text += f", конфигурация {config}"
        return text + "."

    return "Сохранённые параметры есть, но подключение не подтверждено — нужен onec-data_onec_connect."


def format_check_connection_reply(payload: dict[str, Any]) -> str:
    connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
    target = str(connection.get("target") or connection.get("display_name") or "база").strip()
    via = str(payload.get("via") or "com").strip()
    return f"Связь с базой «{target}» в порядке ({via})."


def format_save_case_reply(status: str) -> str:
    if str(status).lower() == "final":
        return "Кейс сохранён как подтверждённое решение."
    return "Черновик кейса сохранён для архива."


def format_get_case_reply(summary: dict[str, Any]) -> str:
    symptom = str(summary.get("symptom") or "").strip()
    preview = str(summary.get("solutionPreview") or "").strip()
    warning = str(summary.get("warning") or "").strip()

    parts = []
    if symptom:
        parts.append(symptom)
    if preview:
        parts.append(preview)
    if warning:
        parts.append(warning)

    return " ".join(parts) if parts else "Кейс загружен."


def compact_search_payload(raw: dict[str, Any]) -> dict[str, Any]:
    summaries = raw.get("userSummaries") or []
    reply = format_cases_reply(summaries)
    return wrap_agent_response(
        reply,
        count=raw.get("count", 0),
        sameConfigurationCount=raw.get("sameConfigurationCount", 0),
        mustReviewBeforeInvestigation=raw.get("mustReviewBeforeInvestigation", False),
        userSummaries=summaries,
        caseIds=[str(item.get("id") or "") for item in summaries if item.get("id")],
        query=raw.get("query", ""),
        agent_action=(
            "AGENT_ACTION: пользователю — только replyToUser. "
            "Детали кейса: onec-data_onec_get_case(case_id). matches в ответе нет намеренно."
        ),
    )


def format_infobases_reply(bases: list[dict[str, Any]]) -> str:
    if not bases:
        return "В реестре Windows не найдено информационных баз."

    lines: list[str] = ["Доступные базы:"]
    for index, item in enumerate(bases, start=1):
        name = str(item.get("display_name") or item.get("name") or f"База {index}").strip()
        path = str(item.get("info_base_path") or item.get("path") or "").strip()
        line = f"{index}. {name}"
        if path:
            line += f" — {path}"
        lines.append(line)
    return "\n".join(lines)


def welcome_plain_text(payload: dict[str, Any]) -> str:
    reset = payload.get("session_reset") if isinstance(payload.get("session_reset"), dict) else {}
    reply = str(payload.get("formatted_user") or payload.get("greeting") or "").strip()

    if reset.get("disconnected") and reset.get("previous_target"):
        reply += (
            f"\n\nПредыдущее подключение ({reset.get('previous_target')}) сброшено — "
            "нужны база и пароль заново."
        )

    return reply


def format_metadata_status_reply(payload: dict[str, Any]) -> str:
    if not payload.get("ready"):
        message = str(payload.get("message") or "").strip()
        if message:
            return message
        return "Кэш метаданных не готов. Выполните onec-data_onec_refresh_metadata после подключения."

    name = str(payload.get("configurationName") or "конфигурация").strip()
    version = str(payload.get("version") or "").strip()
    count = payload.get("objectCount", 0)
    text = f"Метаданные готовы: {name}"
    if version and version != "unknown":
        text += f", версия {version}"
    if count:
        text += f", объектов {count}"
    return text + "."


def format_investigation_status_reply(payload: dict[str, Any]) -> str:
    if not payload.get("active"):
        return "Активного расследования в этой сессии нет."
    symptom = str(payload.get("symptom") or "").strip()
    status = str(payload.get("status") or "draft").strip()
    if symptom:
        return f"Активное расследование ({status}): {symptom[:200]}."
    return f"Активное расследование, статус {status}."


def format_refresh_metadata_reply(manifest: dict[str, Any]) -> str:
    name = str(manifest.get("configurationName") or "конфигурация").strip()
    version = str(manifest.get("version") or "").strip()
    count = manifest.get("objectCount", 0)
    text = f"Метаданные обновлены: {name}"
    if version and version != "unknown":
        text += f", версия {version}"
    if count:
        text += f", объектов {count}"
    return text + "."


def format_bridge_status_reply(payload: dict[str, Any]) -> str:
    if not payload.get("configured"):
        return "Bridge не настроен — запросы к базе через обычный COM."
    if payload.get("readyForQuery"):
        label = str(payload.get("infoBaseLabel") or "").strip()
        if label:
            return f"Bridge готов для запросов к базе «{label}»."
        return "Bridge готов для запросов к базе."
    message = str(payload.get("message") or "").strip()
    if message:
        return message
    return "Bridge настроен, но агент не в сети — перезапустите Start-OpenCode.cmd."
