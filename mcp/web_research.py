"""Фасад веб-исследований для MCP onec-data."""

from __future__ import annotations

from typing import Any

from forum_search import search_forums
from its_client import ITS_DATABASES, ItsClient
from its_session import AGENT_ACTION_ITS_CREDENTIALS, clear_its_credentials, public_its_view, save_its_credentials
from web_config import its_credentials_configured, load_web_config


def _its_not_configured_payload(action: str = "") -> dict[str, Any]:
    return {
        "source": "its",
        "authenticated": False,
        "its_credentials_configured": False,
        "agent_action": action or AGENT_ACTION_ITS_CREDENTIALS,
        "results": [],
        "text": "",
    }


def web_research_status(root, its_memory: dict[str, str] | None = None) -> dict[str, Any]:
    config = load_web_config(root, its_memory)
    configured = its_credentials_configured(config)
    public = public_its_view(config)

    payload: dict[str, Any] = {
        "its_credentials_configured": configured,
        "its_user": public.get("its_user", ""),
        "its_databases": ITS_DATABASES,
        "forum_sites": config.get("forum_sites", []),
        "verify_ssl": config.get("verify_ssl", True),
        "guidance": (
            "ИТС — авторитетный источник (onec_its_search / onec_its_fetch). "
            "Форумы — только для идей; проверяй версию конфигурации и метаданные базы."
        ),
    }

    if configured:
        payload["message"] = "Учётные данные ИТС настроены. Можно вызывать onec_its_search / onec_its_fetch."
    else:
        payload["message"] = AGENT_ACTION_ITS_CREDENTIALS
        payload["agent_action"] = AGENT_ACTION_ITS_CREDENTIALS

    return payload


def configure_its_payload(
    root,
    user: str,
    password: str,
    its_memory: dict[str, str],
) -> dict[str, Any]:
    saved = save_its_credentials(root, user, password)
    its_memory.clear()
    its_memory.update(saved)

    config = load_web_config(root, its_memory)
    client = ItsClient(config)
    try:
        auth = client.authenticate()
    finally:
        client.close()

    payload: dict[str, Any] = {
        "status": "ok" if auth.get("ok") else "auth_failed",
        "its_credentials_configured": auth.get("ok", False),
        "its_user": saved["user"],
        "auth": auth,
    }

    if auth.get("ok"):
        payload["message"] = "Доступ к ИТС настроен. Можно вызывать onec_its_search / onec_its_fetch."
    else:
        payload["agent_action"] = (
            "AGENT_ACTION: авторизация не прошла — уточни логин/пароль у пользователя "
            "и повтори onec_its_configure. Не повторяй пароль в ответе."
        )
        payload["message"] = auth.get("message", "Ошибка авторизации ИТС.")

    return payload


def clear_its_payload(root, its_memory: dict[str, str]) -> dict[str, Any]:
    clear_its_credentials(root)
    its_memory.clear()
    return {
        "its_credentials_configured": False,
        "message": "Учётные данные ИТС сброшены.",
    }


def search_forums_payload(
    root,
    query: str,
    configuration_name: str = "",
    configuration_version: str = "",
    limit: int = 5,
    its_memory: dict[str, str] | None = None,
) -> dict[str, Any]:
    config = load_web_config(root, its_memory)
    return search_forums(
        config,
        query,
        configuration_name=configuration_name,
        configuration_version=configuration_version,
        limit=limit,
    )


def search_its_payload(
    root,
    query: str,
    database: str = "v8std",
    limit: int = 5,
    its_memory: dict[str, str] | None = None,
) -> dict[str, Any]:
    config = load_web_config(root, its_memory)
    if not its_credentials_configured(config):
        payload = _its_not_configured_payload()
        payload["query"] = query.strip()
        payload["database"] = database
        return payload

    client = ItsClient(config)
    try:
        payload = client.search(query, database=database, limit=limit)
        if not payload.get("authenticated") and payload.get("error"):
            payload["agent_action"] = (
                "AGENT_ACTION: проверь onec_web_research_status; при необходимости "
                "спроси логин/пароль ИТС и вызови onec_its_configure."
            )
        payload["guidance"] = (
            "ИТС — приоритетный источник. Укажи в ответе ссылку на статью и "
            "проверь применимость к версии конфигурации пользователя."
        )
        return payload
    finally:
        client.close()


def fetch_its_payload(
    root,
    url: str,
    max_chars: int = 12000,
    its_memory: dict[str, str] | None = None,
) -> dict[str, Any]:
    config = load_web_config(root, its_memory)
    if not its_credentials_configured(config) and "its.1c.ru" in url.lower():
        payload = _its_not_configured_payload()
        payload["url"] = url.strip()
        return payload

    client = ItsClient(config)
    try:
        payload = client.fetch(url, max_chars=max_chars)
        if not payload.get("authenticated") and payload.get("error"):
            payload["agent_action"] = (
                "AGENT_ACTION: спроси логин/пароль ИТС у пользователя и вызови onec_its_configure."
            )
        return payload
    finally:
        client.close()
