"""Приветствие и список возможностей аналитика 1С для новой сессии."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from connection_session import load_session, public_view, resolve_connection
from metadata_cache import metadata_status


def _user_task_menu() -> list[dict[str, str]]:
    """Варианты для окна question — понятные пользователю, без MCP."""
    return [
        {
            "id": "investigation",
            "label": "Разобрать ошибку или расхождение в учёте",
            "hint": "skill 1c-investigation-pipeline; режим live/offline",
        },
        {
            "id": "requirements",
            "label": "Оформить лист требований на доработку",
            "hint": "skill 1c-requirements-sheet",
        },
        {
            "id": "mechanism",
            "label": "Объяснить, как устроен механизм в конфигурации",
            "hint": "ИТС, метаданные, при необходимости код из XML",
        },
        {
            "id": "research",
            "label": "Общий вопрос по платформе 1С или методологии",
            "hint": "skill 1c-web-research; без базы",
        },
        {
            "id": "continue",
            "label": "Уже описал задачу в сообщении — продолжить с ней",
            "hint": "Определить тип по first_user_message, не показывать меню повторно",
        },
    ]


def _capabilities() -> list[dict[str, str]]:
    return [
        {
            "group": "Подключение и данные",
            "items": [
                "onec_list_infobases — список баз из реестра Windows",
                "onec_connect — подключение к ИБ (read-only)",
                "onec_connection_status / onec_check_connection — статус сессии",
                "onec_disconnect — сброс подключения",
                "onec_bridge_status — Bridge Agent (оркестратор + долгий COM для onec_query)",
                "onec_query — запрос ВЫБРАТЬ/SELECT (через Bridge или COM, по согласию)",
            ],
        },
        {
            "group": "Метаданные конфигурации",
            "items": [
                "onec_metadata_status — готовность кэша",
                "onec_metadata_search — поиск объектов по имени/синониму",
                "onec_metadata_object — карточка объекта (реквизиты, ТЧ)",
                "onec_refresh_metadata — обновить кэш из ИБ",
            ],
        },
        {
            "group": "Документация и интернет",
            "items": [
                "onec_web_research_status — настройка ИТС",
                "onec_its_configure — логин/пароль портала ИТС",
                "onec_its_search / onec_its_fetch — поиск в 1С:ИТС",
                "onec_web_search_forums — форумы (гипотезы, версия конфигурации)",
            ],
        },
        {
            "group": "Код и расследование",
            "items": [
                "onec_config_sources_status / onec_config_sources_register — XML-исходники (спросить путь у пользователя)",
                "onec_dump_config — выгрузка конфигурации в файлы (partial/full, нужен connect)",
                "onec_config_read_module / onec_config_search_code — анализ BSL из XML",
                "onec_read_module — запасной: модуль через конфигуратор (COM не читает код)",
                "onec_set_task_type — выбор в question (investigation, requirements, …); не симптом",
                "onec_declare_symptom — текстовое описание задачи от пользователя (не label кнопки)",
                "onec_search_cases / onec_get_case — библиотека кейсов",
                "onec_save_case — draft при приближении к решению, final в конце; дополнять по case_id",
                "onec_investigation_status — активный case_id и пути заметок",
            ],
        },
        {
            "group": "Obsidian — архив аналитика",
            "items": [
                "onec_obsidian_status — путь vault и проекты",
                "onec_obsidian_set_context — имя папки ИБ (если нет connect)",
                "onec_obsidian_save_requirements — лист требований",
                "onec_obsidian_save_session — заметка сессии (вместе с draft-кейсом)",
                "onec_obsidian_append_session — дополнение заметки при уточнениях",
                "onec_obsidian_prepare_requirements — контекст перед ЛТ (кейсы, справочники)",
                "onec_bitmedic_guidance — поиск на info.bitmedic.ru (БИТ.Медицина)",
            ],
        },
        {
            "group": "Лист требований",
            "items": [
                "skill 1c-requirements-sheet — черновик ЛТ из описания или транскрипта",
                "фаза A: ЛТ в чат (§2.1 ценность, §4 подробно, §7 трудочасы) + onec_obsidian_save_requirements (draft)",
                "фаза B: после connect — уточнить §4 и §7, ЛТ final в Obsidian",
            ],
        },
    ]


def build_welcome_payload(
    root: Path,
    memory_session: dict[str, str] | None,
    session_reset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    connection = resolve_connection(root, memory_session)
    session_saved = load_session(root) is not None

    connection_block: dict[str, Any] = {
        "session_saved": session_saved,
        "connected": False,
        "target": "",
        "user": "",
        "metadata_ready": False,
    }

    if connection:
        view = public_view(connection)
        connection_block.update(
            {
                "target": view.get("target", ""),
                "user": view.get("user", ""),
                "target_type": view.get("target_type", ""),
            }
        )
        cache_relative = connection.get("metadata_cache", "").strip() or None
        meta = metadata_status(root, cache_relative, connection)
        connection_block["metadata_ready"] = bool(meta.get("ready"))
        connection_block["configuration_name"] = meta.get("configurationName", "")
        connection_block["configuration_version"] = meta.get("version", "")

    connection_block["hint"] = (
        "Подключение не активно. Для live-режима: onec_list_infobases → "
        "спросите базу, пользователя и пароль → onec_connect. "
        "Или предложите offline/research без ИБ."
    )

    greeting = (
        "Здравствуйте! Я аналитик 1С. "
        "Помогаю с ошибками учёта, листами требований, разбором механизмов и вопросами по платформе."
    )

    user_menu = _user_task_menu()
    question_block = {
        "title": "Чем помочь?",
        "prompt": "Выберите тип задачи — дальше уточню детали и при необходимости подключение к базе.",
        "options": [{"id": item["id"], "label": item["label"]} for item in user_menu],
    }

    pipeline = (
        "Типовой порядок (live): подключение -> метаданные -> ИТС -> "
        "чек-лист для ИБ -> при необходимости код из XML-исходников."
    )

    reset_block: dict[str, Any] = session_reset or {}
    if reset_block.get("disconnected"):
        connection_block["session_saved"] = False
        connection_block["connected"] = False
        connection_block["hint"] = (
            "Сохранённое подключение сброшено (новая чат-сессия). "
            "onec_list_infobases → спросите базу, пользователя и пароль → onec_connect."
        )
        if reset_block.get("previous_target"):
            connection_block["previous_target"] = reset_block["previous_target"]

    return {
        "greeting": greeting,
        "pipeline": pipeline,
        "user_menu": user_menu,
        "question": question_block,
        "capabilities": _capabilities(),
        "connection": connection_block,
        "session_reset": reset_block,
        "modes": [
            {"id": "live", "description": "Есть доступ к ИБ — connect, метаданные, ИТС, код"},
            {"id": "offline", "description": "Нет доступа к ИБ — описание, кейсы, ИТС, форумы"},
            {"id": "research", "description": "Общий вопрос — ИТС и интернет без базы"},
        ],
        "agent_action": (
            "AGENT_ACTION: 1) Покажите пользователю только formatted_user (коротко, без MCP). "
            "2) Сразу в том же ответе вызовите question с title/prompt/options из поля question. "
            "3) Не выводите formatted, JSON инструментов, кейсы, onec_save_case в чат. "
            "4) До question запрещены onec_search_cases, onec_connect, onec_save_case. "
            "5) После выбора — уточните задачу; при live — база."
        ),
        "first_step": (
            "Дождаться выбора в question. Затем спросить суть задачи своими словами. "
            "onec_search_cases — только после описания симптома пользователем."
        ),
    }


def format_welcome_user_text(payload: dict[str, Any]) -> str:
    """Короткий текст для пользователя — без перечня MCP-инструментов."""
    lines = [
        payload.get("greeting", ""),
        "",
        "Выберите тип задачи в форме ниже — так быстрее перейдём к делу.",
    ]
    reset = payload.get("session_reset") or {}
    if reset.get("disconnected") and reset.get("previous_target"):
        lines.extend(
            [
                "",
                f"*(Сохранённое подключение к «{reset['previous_target']}» сброшено — "
                "для работы с базой уточню доступ заново.)*",
            ]
        )
    return "\n".join(lines)


def format_welcome_text(payload: dict[str, Any]) -> str:
    lines: list[str] = [
        payload.get("greeting", ""),
        "",
        payload.get("pipeline", ""),
        "",
        "## Доступные функции (MCP onec-data)",
    ]

    for group in payload.get("capabilities", []):
        title = group.get("group", "")
        if title:
            lines.append(f"\n### {title}")
        for item in group.get("items", []):
            lines.append(f"- {item}")

    conn = payload.get("connection", {})
    reset = payload.get("session_reset") or {}
    lines.extend(
        [
            "",
            "## Подключение",
            f"- Сессия сохранена: {'да' if conn.get('session_saved') else 'нет'}",
        ]
    )
    if reset.get("previous_target"):
        lines.append(f"- Предыдущая база (сброшена): {reset['previous_target']}")
    elif conn.get("target"):
        lines.append(f"- База: {conn['target']}")
    if reset.get("previous_user"):
        lines.append(f"- Предыдущий пользователь (сброшен): {reset['previous_user']}")
    elif conn.get("user"):
        lines.append(f"- Пользователь: {conn['user']}")
    if conn.get("configuration_name"):
        lines.append(
            f"- Конфигурация в кэше: {conn['configuration_name']} "
            f"({conn.get('configuration_version', '')})"
        )
    lines.append(f"- Кэш метаданных готов: {'да' if conn.get('metadata_ready') else 'нет'}")
    if conn.get("hint"):
        lines.append(f"- {conn['hint']}")

    if reset.get("disconnected"):
        lines.extend(
            [
                "",
                "## Сброс сессии",
                f"- {reset.get('reason', 'Новая чат-сессия: сохранённое подключение сброшено.')}",
                "- Дальше: onec_list_infobases → спросить базу, пользователя, пароль → onec_connect.",
            ]
        )

    lines.extend(["", payload.get("first_step", "")])
    return "\n".join(lines)


def welcome_payload_json(
    root: Path,
    memory_session: dict[str, str] | None,
    session_reset: dict[str, Any] | None = None,
) -> str:
    from agent_reply import welcome_plain_text

    payload = build_welcome_payload(root, memory_session, session_reset=session_reset)
    payload["formatted_user"] = format_welcome_user_text(payload)
    payload["formatted"] = format_welcome_text(payload)
    return welcome_plain_text(payload)
