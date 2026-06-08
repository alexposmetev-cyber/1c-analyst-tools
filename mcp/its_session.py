"""Сессия учётных данных ИТС (память MCP + .onec-web.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WEB_CONFIG_FILENAME = ".onec-web.json"

AGENT_ACTION_ITS_CREDENTIALS = (
    "AGENT_ACTION: спроси у пользователя логин и пароль портала 1С:ИТС "
    "(инструмент question), затем вызови onec_its_configure. "
    "Не предлагай редактировать .onec-web.json вручную и не проси перезапуск OpenCode."
)


def web_config_path(root: Path) -> Path:
    return root / WEB_CONFIG_FILENAME


def load_web_file(root: Path) -> dict[str, Any]:
    path = web_config_path(root)
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def save_its_credentials(root: Path, user: str, password: str) -> dict[str, Any]:
    user = user.strip()
    if not user:
        raise ValueError("Параметр user обязателен.")
    if not password:
        raise ValueError("Параметр password обязателен для доступа к ИТС.")

    payload = load_web_file(root)
    its = payload.get("its")
    if not isinstance(its, dict):
        its = {}
    its["user"] = user
    its["password"] = password
    payload["its"] = its

    web_config_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"user": user, "password": password}


def clear_its_credentials(root: Path) -> None:
    payload = load_web_file(root)
    its = payload.get("its")
    if isinstance(its, dict):
        its.pop("user", None)
        its.pop("password", None)
        payload["its"] = its
        web_config_path(root).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def apply_memory_its(config: dict[str, Any], memory: dict[str, str] | None) -> dict[str, Any]:
    if not memory:
        return config

    its = config.setdefault("its", {})
    if not isinstance(its, dict):
        its = {}
        config["its"] = its

    user = memory.get("user", "").strip()
    password = memory.get("password", "")

    if user:
        its["user"] = user
    if password:
        its["password"] = password

    return config


def public_its_view(config: dict[str, Any]) -> dict[str, Any]:
    its = config.get("its", {})
    if not isinstance(its, dict):
        its = {}

    user = str(its.get("user", "")).strip()
    return {
        "its_credentials_configured": bool(user) and bool(str(its.get("password", "")).strip()),
        "its_user": user,
    }
