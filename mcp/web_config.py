"""Настройки веб-поиска (ИТС, форумы) — env и .onec-web.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from its_session import apply_memory_its


def load_web_config(root: Path, its_memory: dict[str, str] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "its": {
            "user": os.environ.get("ONEC_ITS_USER", "").strip(),
            "password": os.environ.get("ONEC_ITS_PASSWORD", "").strip(),
            "login_url": "https://login.1c.ru/login",
            "service_url": "https://its.1c.ru/login/cas",
        },
        "forum_sites": [
            "infostart.ru",
            "forum.mista.ru",
            "forum.infostart.ru",
            "kb.1c.ru",
        ],
        "timeout_seconds": 30,
        "verify_ssl": True,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    }

    config_path = root / ".onec-web.json"
    if config_path.is_file():
        file_payload = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(file_payload, dict):
            _merge_dict(config, file_payload)

    its = config.setdefault("its", {})
    if not isinstance(its, dict):
        its = {}
        config["its"] = its

    env_user = os.environ.get("ONEC_ITS_USER", "").strip()
    env_password = os.environ.get("ONEC_ITS_PASSWORD", "").strip()
    if env_user:
        its["user"] = env_user
    if env_password:
        its["password"] = env_password

    apply_memory_its(config, its_memory)

    verify_env = os.environ.get("ONEC_WEB_VERIFY_SSL", "").strip().lower()
    if verify_env in {"0", "false", "no"}:
        config["verify_ssl"] = False
    elif verify_env in {"1", "true", "yes"}:
        config["verify_ssl"] = True

    return config


def its_credentials_configured(config: dict[str, Any]) -> bool:
    its = config.get("its", {})
    if not isinstance(its, dict):
        return False

    return bool(its.get("user")) and bool(its.get("password"))


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dict(base[key], value)
        else:
            base[key] = value
