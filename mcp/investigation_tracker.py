"""Активное расследование в сессии — связь кейса и заметки Sessions для дополнения."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACKER_FILENAME = ".onec-investigation.json"


def _tracker_path(root: Path) -> Path:
    return root / TRACKER_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_tracker(root: Path) -> dict[str, Any] | None:
    path = _tracker_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_tracker(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["updatedAt"] = _now_iso()
    _tracker_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def clear_tracker(root: Path) -> None:
    path = _tracker_path(root)
    if path.is_file():
        path.unlink()


def register_investigation(
    root: Path,
    *,
    case_id: str = "",
    case_relative_path: str = "",
    session_relative_path: str = "",
    requirements_relative_path: str = "",
    requirements_json_path: str = "",
    requirements_id: str = "",
    status: str = "draft",
    symptom: str = "",
) -> dict[str, Any]:
    payload = {
        "caseId": case_id.strip(),
        "caseRelativePath": case_relative_path.strip(),
        "sessionRelativePath": session_relative_path.strip(),
        "requirementsRelativePath": requirements_relative_path.strip(),
        "requirementsJsonPath": requirements_json_path.strip(),
        "requirementsId": requirements_id.strip(),
        "status": status.strip() or "draft",
        "symptom": symptom.strip()[:240],
        "startedAt": _now_iso(),
    }
    existing = load_tracker(root)
    if existing:
        if payload["caseId"] and existing.get("caseId") == payload["caseId"]:
            payload["startedAt"] = existing.get("startedAt", payload["startedAt"])
            if not payload["caseRelativePath"]:
                payload["caseRelativePath"] = str(existing.get("caseRelativePath", ""))
            if not payload["sessionRelativePath"]:
                payload["sessionRelativePath"] = str(existing.get("sessionRelativePath", ""))
        else:
            payload["startedAt"] = existing.get("startedAt", payload["startedAt"])
            if not payload["caseRelativePath"]:
                payload["caseRelativePath"] = str(existing.get("caseRelativePath", ""))
            if not payload["sessionRelativePath"]:
                payload["sessionRelativePath"] = str(existing.get("sessionRelativePath", ""))
            if not payload["requirementsRelativePath"]:
                payload["requirementsRelativePath"] = str(existing.get("requirementsRelativePath", ""))
            if not payload["requirementsJsonPath"]:
                payload["requirementsJsonPath"] = str(existing.get("requirementsJsonPath", ""))
            if not payload["requirementsId"]:
                payload["requirementsId"] = str(existing.get("requirementsId", ""))
    return save_tracker(root, payload)


def update_tracker_paths(
    root: Path,
    *,
    case_relative_path: str = "",
    session_relative_path: str = "",
    requirements_relative_path: str = "",
    requirements_json_path: str = "",
    requirements_id: str = "",
    status: str = "",
) -> dict[str, Any] | None:
    payload = load_tracker(root)
    if not payload:
        return None
    if case_relative_path.strip():
        payload["caseRelativePath"] = case_relative_path.strip()
    if session_relative_path.strip():
        payload["sessionRelativePath"] = session_relative_path.strip()
    if requirements_relative_path.strip():
        payload["requirementsRelativePath"] = requirements_relative_path.strip()
    if requirements_json_path.strip():
        payload["requirementsJsonPath"] = requirements_json_path.strip()
    if requirements_id.strip():
        payload["requirementsId"] = requirements_id.strip()
    if status.strip():
        payload["status"] = status.strip()
    return save_tracker(root, payload)


def tracker_status(root: Path) -> dict[str, Any]:
    payload = load_tracker(root)
    if not payload:
        return {
            "active": False,
            "agent_action": (
                "AGENT_ACTION: при приближении к решению — onec_save_case(status=draft) "
                "и onec_obsidian_save_session; при доп. вопросах — дополнять через "
                "onec_save_case(case_id=...) и onec_obsidian_append_session."
            ),
        }
    return {
        "active": True,
        "case_id": payload.get("caseId", ""),
        "case_relative_path": payload.get("caseRelativePath", ""),
        "session_relative_path": payload.get("sessionRelativePath", ""),
        "requirements_relative_path": payload.get("requirementsRelativePath", ""),
        "requirements_json_path": payload.get("requirementsJsonPath", ""),
        "requirements_id": payload.get("requirementsId", ""),
        "status": payload.get("status", "draft"),
        "symptom": payload.get("symptom", ""),
        "started_at": payload.get("startedAt", ""),
        "updated_at": payload.get("updatedAt", ""),
        "agent_action": (
            "AGENT_ACTION: дополняйте тот же кейс (case_id), лист требований "
            "(requirements_relative_path) и заметку сессии (session_relative_path), "
            "не создавайте дубликаты."
        ),
    }
