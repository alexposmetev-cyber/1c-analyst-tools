"""Сопоставление упоминания конфигурации в сообщении пользователя с сохранённой сессией."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from connection_session import connection_target_key, load_session, public_view, resolve_connection
from metadata_cache import metadata_status

# Ключ — внутренний идентификатор; значения — фразы для поиска в нормализованном тексте.
CONFIGURATION_ALIASES: dict[str, tuple[str, ...]] = {
    "bit_medicine": (
        "бит",
        "bitmedic",
        "бит.медицин",
        "управлениемедицинским",
        "управлениемедицинскимцентром",
        "битуправление",
    ),
    "ut": (
        "ут11",
        "ут10",
        "управлениеторговлей",
        "ut ",
        "1сут",
        "1cut",
    ),
    "erp": (
        "1сerp",
        "1cerp",
        "erp ",
    ),
    "accounting": (
        "бухгалтерия",
        "бухгалтерии",
        "бп3",
        "бп 3",
        "demoaccounting",
        "бухгалтерияпредприятия",
    ),
    "zup": (
        "зуп",
        "зарплатаикадры",
        "зарплата",
    ),
    "crm": (
        "crm",
        "срм",
    ),
    "retail": (
        "розница",
        "retail",
    ),
}


def _normalize_text(value: str) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^\w\d]+", "", text, flags=re.UNICODE)
    return text


def _alias_keys_in_text(normalized_message: str) -> set[str]:
    if not normalized_message:
        return set()

    found: set[str] = set()
    for key, phrases in CONFIGURATION_ALIASES.items():
        for phrase in phrases:
            token = _normalize_text(phrase)
            if token and token in normalized_message:
                found.add(key)
                break
    return found


def _session_text_blobs(session: dict[str, str], meta: dict[str, Any] | None) -> list[str]:
    blobs: list[str] = []
    for field in (
        "configuration_name",
        "info_base_display_name",
        "obsidian_database",
        "info_base_path",
        "metadata_fingerprint",
        "metadata_library",
    ):
        value = str(session.get(field, "")).strip()
        if value:
            blobs.append(value)

    if meta:
        for field in ("configurationName", "configurationSynonym", "target"):
            value = str(meta.get(field, "")).strip()
            if value:
                blobs.append(value)

    return blobs


def _alias_keys_for_session(session: dict[str, str], meta: dict[str, Any] | None) -> set[str]:
    combined = _normalize_text(" ".join(_session_text_blobs(session, meta)))
    if not combined:
        return set()

    keys: set[str] = set()
    for key, phrases in CONFIGURATION_ALIASES.items():
        for phrase in phrases:
            token = _normalize_text(phrase)
            if token and token in combined:
                keys.add(key)
                break

    # Имя каталога базы / конфигурации без словаря (например DemoAccounting).
    path = str(session.get("info_base_path", "")).strip()
    if path:
        folder = _normalize_text(Path(path).name)
        if len(folder) >= 4 and folder not in combined:
            combined = f"{combined}{folder}"

    for key, phrases in CONFIGURATION_ALIASES.items():
        if key in keys:
            continue
        for phrase in phrases:
            token = _normalize_text(phrase)
            if token and token in combined:
                keys.add(key)
                break

    return keys


def _extract_info_base_path_from_message(message: str) -> str:
    patterns = [
        r'File="([^"]+)"',
        r"File='([^']+)'",
        r'[A-Za-z]:\\[^\s"\']+',
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip() if match.lastindex else match.group(0).strip()
    return ""


def evaluate_configuration_mismatch(
    root: Path,
    memory_session: dict[str, str] | None,
    first_user_message: str,
) -> dict[str, Any]:
    """Решает, нужно ли сбросить сессию перед работой в новой чат-сессии."""
    message = (first_user_message or "").strip()
    connection = resolve_connection(root, memory_session)

    result: dict[str, Any] = {
        "should_disconnect": False,
        "reason": "",
        "user_configuration_keys": [],
        "session_configuration_keys": [],
        "previous_target": "",
        "mentioned_path": "",
    }

    if not connection:
        return result

    view = public_view(connection)
    result["previous_target"] = view.get("target", "")

    cache_relative = connection.get("metadata_cache", "").strip() or None
    meta = metadata_status(root, cache_relative, connection)

    user_keys = _alias_keys_in_text(_normalize_text(message))
    session_keys = _alias_keys_for_session(connection, meta)

    result["user_configuration_keys"] = sorted(user_keys)
    result["session_configuration_keys"] = sorted(session_keys)

    mentioned_path = _extract_info_base_path_from_message(message)
    result["mentioned_path"] = mentioned_path
    if mentioned_path:
        current_path = connection.get("info_base_path", "").strip()
        if current_path and _normalize_text(current_path) != _normalize_text(mentioned_path):
            result["should_disconnect"] = True
            result["reason"] = (
                "В сообщении указан другой каталог информационной базы, "
                "чем в сохранённой сессии."
            )
            return result

    if not user_keys:
        return result

    if not session_keys:
        # Явно названа конфигурация, в сессии нет распознанной — не сбрасываем автоматически.
        return result

    if user_keys.isdisjoint(session_keys):
        user_label = ", ".join(result["user_configuration_keys"])
        session_label = ", ".join(result["session_configuration_keys"]) or view.get("target", "")
        result["should_disconnect"] = True
        result["reason"] = (
            f"В первом сообщении упомянута конфигурация ({user_label}), "
            f"а сохранённая сессия относится к другой ({session_label}). "
            "Сессия сброшена — нужен новый onec_connect."
        )

    return result


def apply_configuration_mismatch_reset(
    root: Path,
    memory_session: dict[str, str] | None,
    first_user_message: str,
    *,
    clear_memory: Any,
    clear_verified: Any,
    clear_session_file: Any,
) -> dict[str, Any]:
    """При несовпадении конфигурации очищает сессию и возвращает отчёт."""
    evaluation = evaluate_configuration_mismatch(root, memory_session, first_user_message)
    if evaluation.get("should_disconnect"):
        clear_memory()
        clear_verified()
        clear_session_file(root)
        evaluation["disconnected"] = True
    else:
        evaluation["disconnected"] = False

    return evaluation


def reset_session_for_new_chat(
    root: Path,
    memory_session: dict[str, str] | None,
    first_user_message: str,
    *,
    clear_memory: Any,
    clear_verified: Any,
    clear_session_file: Any,
) -> dict[str, Any]:
    """Сбрасывает сохранённое подключение при старте новой чат-сессии (onec_welcome)."""
    had_file = load_session(root) is not None
    connection = resolve_connection(root, memory_session)
    previous_target = ""
    previous_user = ""

    if connection:
        view = public_view(connection)
        previous_target = str(view.get("target", "")).strip()
        previous_user = str(view.get("user", "")).strip()

    mismatch = evaluate_configuration_mismatch(root, memory_session, first_user_message)

    had_previous = bool(connection) or had_file
    clear_memory()
    clear_verified()
    clear_session_file(root)

    if mismatch.get("should_disconnect") and mismatch.get("reason"):
        reason = str(mismatch["reason"])
    elif previous_target:
        reason = (
            f"Новая чат-сессия: сброшено сохранённое подключение к «{previous_target}». "
            "Выберите базу, пользователя и пароль заново → onec_connect."
        )
    else:
        reason = (
            "Новая чат-сессия: подключение не активно. "
            "Для live-режима: onec_list_infobases → выбор базы и учётных данных → onec_connect."
        )

    return {
        "disconnected": True,
        "had_previous_session": had_previous,
        "previous_target": previous_target,
        "previous_user": previous_user,
        "reason": reason,
        "user_configuration_keys": mismatch.get("user_configuration_keys", []),
        "session_configuration_keys": mismatch.get("session_configuration_keys", []),
        "mentioned_path": mismatch.get("mentioned_path", ""),
    }
