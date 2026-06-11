"""Клиент 1C Bridge Agent (оркестратор poll/enqueue) для MCP / OpenCode."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

BRIDGE_CONFIG_CANDIDATES = (
    ROOT / "bridge" / "agent" / "bridge-agent.json",
    ROOT / ".onec-bridge.json",
)

AGENT_STALE_SEC = 90
DEFAULT_JOB_TIMEOUT_SEC = 120


def _normalize_path(value: str) -> str:
    text = (value or "").strip().replace("/", "\\").rstrip("\\").lower()
    if text.startswith('file="') and text.endswith('"'):
        text = text[6:-1]
    return text


def bridge_target_key(connection: dict[str, Any]) -> str:
    path = _normalize_path(str(connection.get("info_base_path") or ""))
    if path:
        return f"file:{path}"

    server = str(connection.get("server") or "").strip().lower()
    ref = str(connection.get("ref") or "").strip().lower()
    return f"server:{server}/{ref}"


def load_bridge_config() -> dict[str, Any] | None:
    for path in BRIDGE_CONFIG_CANDIDATES:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("bridge_id") and data.get("bridge_token"):
            data["_config_path"] = str(path)
            return data
    return None


def orchestrator_base_url(config: dict[str, Any] | None = None) -> str:
    if config:
        url = str(config.get("orchestrator_url") or "").strip()
        if url:
            return url.rstrip("/")
    env_url = os.environ.get("ONEC_BRIDGE_ORCHESTRATOR_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    return "http://127.0.0.1:8787"


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Оркестратор недоступен ({url}): {exc.reason}") from exc

    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError("Неожиданный ответ оркестратора.")
    return parsed


def orchestrator_health(config: dict[str, Any] | None = None) -> dict[str, Any]:
    base = orchestrator_base_url(config)
    try:
        payload = _http_json("GET", f"{base}/health", timeout_sec=5)
        return {"ok": payload.get("status") == "ok", "url": base, "detail": payload}
    except RuntimeError as exc:
        return {"ok": False, "url": base, "error": str(exc)}


def bridge_agent_info(config: dict[str, Any]) -> dict[str, Any] | None:
    base = orchestrator_base_url(config)
    bridge_id = str(config.get("bridge_id") or "").strip()
    payload = _http_json("GET", f"{base}/api/bridges", timeout_sec=10)
    bridges = payload.get("bridges")
    if not isinstance(bridges, list):
        return None
    for item in bridges:
        if isinstance(item, dict) and str(item.get("bridge_id") or "") == bridge_id:
            return item
    return None


def session_matches_bridge(session: dict[str, str], config: dict[str, Any]) -> bool:
    connection = config.get("connection")
    if not isinstance(connection, dict):
        return False
    session_key = bridge_target_key(session)
    bridge_key = bridge_target_key(connection)
    if not session_key or not bridge_key:
        return False
    return session_key == bridge_key


def bridge_is_usable_for_session(
    session: dict[str, str] | None,
    config: dict[str, Any] | None = None,
) -> bool:
    cfg = config or load_bridge_config()
    if not cfg or not session:
        return False
    if not session_matches_bridge(session, cfg):
        return False
    health = orchestrator_health(cfg)
    if not health.get("ok"):
        return False
    agent = bridge_agent_info(cfg)
    if not agent:
        return False
    last_poll = agent.get("last_poll_at")
    if last_poll is None:
        return False
    return (time.time() - float(last_poll)) <= AGENT_STALE_SEC


def bridge_status_payload(session: dict[str, str] | None = None) -> dict[str, Any]:
    config = load_bridge_config()
    if not config:
        return {
            "configured": False,
            "message": (
                "Bridge не настроен. Создайте bridge/agent/bridge-agent.json "
                "и запустите оркестратор + Bridge-Agent."
            ),
        }

    health = orchestrator_health(config)
    agent = bridge_agent_info(config) if health.get("ok") else None
    connection = config.get("connection") if isinstance(config.get("connection"), dict) else {}
    last_poll = agent.get("last_poll_at") if agent else None
    agent_online = (
        last_poll is not None and (time.time() - float(last_poll)) <= AGENT_STALE_SEC
    )

    payload: dict[str, Any] = {
        "configured": True,
        "configPath": config.get("_config_path", ""),
        "bridgeId": config.get("bridge_id", ""),
        "orchestratorUrl": orchestrator_base_url(config),
        "orchestratorOk": bool(health.get("ok")),
        "agentOnline": agent_online,
        "agentLastPollAt": last_poll,
        "bridgeTarget": bridge_target_key(connection),
        "readyForQuery": False,
    }

    if health.get("error"):
        payload["orchestratorError"] = health["error"]
    if agent:
        payload["pendingJobs"] = agent.get("pending_jobs", 0)
        payload["infoBaseLabel"] = agent.get("info_base_label", "")

    if session:
        payload["sessionTarget"] = bridge_target_key(session)
        payload["sessionMatchesBridge"] = session_matches_bridge(session, config)

    payload["readyForQuery"] = bool(
        payload.get("orchestratorOk")
        and payload.get("agentOnline")
        and (not session or payload.get("sessionMatchesBridge"))
    )

    if payload["readyForQuery"]:
        payload["message"] = "onec-data_onec_query идёт через Bridge Agent (долгий COM)."
    elif not payload.get("orchestratorOk"):
        payload["message"] = "Запустите bridge\\Start-Orchestrator.cmd"
    elif not payload.get("agentOnline"):
        payload["message"] = "Запустите bridge\\Start-BridgeAgent.cmd"
    elif session and not payload.get("sessionMatchesBridge"):
        payload["message"] = (
            "ИБ в onec-data_onec_connect не совпадает с bridge-agent.json — "
            "onec-data_onec_query через COM или обновите конфиг моста."
        )
    else:
        payload["message"] = "Bridge настроен, ожидается onec-data_onec_connect к той же ИБ."

    return payload


def _enqueue_and_wait(
    config: dict[str, Any],
    tool: str,
    arguments: dict[str, Any],
    timeout_sec: int = DEFAULT_JOB_TIMEOUT_SEC,
) -> dict[str, Any]:
    base = orchestrator_base_url(config)
    bridge_id = str(config.get("bridge_id") or "").strip()
    token = str(config.get("bridge_token") or "").strip()
    if not bridge_id or not token:
        raise RuntimeError("bridge_id и bridge_token обязательны в конфиге моста.")

    queued = _http_json(
        "POST",
        f"{base}/api/bridge/enqueue",
        {
            "bridge_id": bridge_id,
            "bridge_token": token,
            "tool": tool,
            "arguments": arguments,
        },
        timeout_sec=30,
    )
    job_id = str(queued.get("job_id") or "").strip()
    if not job_id:
        raise RuntimeError("Оркестратор не вернул job_id.")

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        job = _http_json("GET", f"{base}/api/jobs/{job_id}", timeout_sec=30)
        status = str(job.get("status") or "").lower()
        if status == "ok":
            result = job.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Пустой result от Bridge Agent.")
            return result
        if status == "error":
            raise RuntimeError(str(job.get("error") or "Ошибка Bridge Agent."))
        time.sleep(1.5)

    raise RuntimeError(
        f"Таймаут ожидания job {job_id}. Bridge Agent запущен и подключён к ИБ?"
    )


def bridge_ping(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_bridge_config()
    if not cfg:
        raise RuntimeError("Bridge не настроен.")
    return _enqueue_and_wait(cfg, "ping", {})


def bridge_execute_query(
    query: str,
    max_rows: int = 500,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_bridge_config()
    if not cfg:
        raise RuntimeError("Bridge не настроен.")

    normalized = " ".join(query.split())
    if not normalized.upper().startswith(("ВЫБРАТЬ", "SELECT")):
        raise ValueError("Разрешены только запросы ВЫБРАТЬ/SELECT.")

    if max_rows < 1:
        max_rows = 1
    if max_rows > 5000:
        max_rows = 5000

    result = _enqueue_and_wait(
        cfg,
        "execute_query",
        {"query": query, "max_rows": max_rows},
        timeout_sec=max(120, DEFAULT_JOB_TIMEOUT_SEC),
    )
    return {
        "rowCount": result.get("rowCount", 0),
        "totalRows": result.get("totalRows", 0),
        "columns": result.get("columns", []),
        "data": result.get("rows", []),
        "via": "bridge",
        "bridgeId": cfg.get("bridge_id", ""),
    }


def try_bridge_query_for_session(
    session: dict[str, str],
    query: str,
    max_rows: int,
) -> dict[str, Any] | None:
    config = load_bridge_config()
    if not bridge_is_usable_for_session(session, config):
        return None
    try:
        return bridge_execute_query(query, max_rows=max_rows, config=config)
    except (RuntimeError, ValueError):
        return None
