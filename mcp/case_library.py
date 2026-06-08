"""Библиотека кейсов расследований 1С — обучение на исправлениях аналитика."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def cases_dir(root: Path) -> Path:
    return root / "cases"


def index_path(root: Path) -> Path:
    return cases_dir(root) / "index.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\.]+", text.lower())
    return {word for word in words if len(word) >= 3}


def load_index(root: Path) -> list[dict[str, Any]]:
    path = index_path(root)
    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def save_index(root: Path, items: list[dict[str, Any]]) -> None:
    directory = cases_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    index_path(root).write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_unique_lines(existing: str, addition: str) -> str:
    addition = addition.strip()
    if not addition:
        return existing.strip()
    if not existing.strip():
        return addition
    if addition in existing:
        return existing.strip()
    return f"{existing.strip()}\n\n{addition}"


def _append_unique_list(existing: list[str], additions: list[str]) -> list[str]:
    result = list(existing)
    seen = {item.lower() for item in result}
    for item in additions:
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _append_chronology(existing: list[dict[str, str]], note: str) -> list[dict[str, str]]:
    note = note.strip()
    if not note:
        return existing
    entry = {"at": _now_iso(), "text": note}
    return [entry, *existing][:50]


def save_case(
    root: Path,
    *,
    symptom: str = "",
    correct_solution: str = "",
    wrong_approach: str = "",
    configuration_name: str = "",
    configuration_version: str = "",
    tags: list[str] | None = None,
    queries_used: list[str] | None = None,
    objects_used: list[str] | None = None,
    verified_by_analyst: bool = True,
    case_id: str = "",
    status: str = "",
    context_summary: str = "",
    investigation_path: str = "",
    methods_applied: list[str] | None = None,
    hypotheses: str = "",
    sources_used: list[str] | None = None,
    checklist: str = "",
    additional_notes: str = "",
) -> dict[str, Any]:
    symptom = symptom.strip()
    correct_solution = correct_solution.strip()
    case_id = case_id.strip()

    if case_id:
        case = get_case(root, case_id)
        created_at = str(case.get("createdAt") or _now_iso())
        if not symptom:
            symptom = str(case.get("symptom", "")).strip()
    else:
        if not symptom:
            raise ValueError("symptom обязателен для нового кейса.")
        case_id = uuid.uuid4().hex[:12]
        created_at = _now_iso()
        case = {
            "id": case_id,
            "createdAt": created_at,
            "configurationName": configuration_name.strip(),
            "configurationVersion": configuration_version.strip() or "unknown",
            "symptom": symptom,
            "symptomTags": [],
            "wrongApproach": "",
            "correctSolution": "",
            "queriesUsed": [],
            "objectsUsed": [],
            "contextSummary": "",
            "investigationPath": "",
            "methodsApplied": [],
            "hypotheses": "",
            "sourcesUsed": [],
            "checklist": "",
            "chronology": [],
            "status": "draft",
            "verifiedByAnalyst": verified_by_analyst,
        }

    if symptom:
        case["symptom"] = symptom
    if configuration_name.strip():
        case["configurationName"] = configuration_name.strip()
    if configuration_version.strip():
        case["configurationVersion"] = configuration_version.strip() or "unknown"
    if correct_solution:
        case["correctSolution"] = correct_solution
    if wrong_approach.strip():
        case["wrongApproach"] = _append_unique_lines(str(case.get("wrongApproach", "")), wrong_approach)
    if context_summary.strip():
        case["contextSummary"] = _append_unique_lines(str(case.get("contextSummary", "")), context_summary)
    if investigation_path.strip():
        case["investigationPath"] = _append_unique_lines(str(case.get("investigationPath", "")), investigation_path)
    if hypotheses.strip():
        case["hypotheses"] = _append_unique_lines(str(case.get("hypotheses", "")), hypotheses)
    if checklist.strip():
        case["checklist"] = _append_unique_lines(str(case.get("checklist", "")), checklist)
    if additional_notes.strip():
        case["chronology"] = _append_chronology(list(case.get("chronology") or []), additional_notes)

    if tags:
        case["symptomTags"] = _append_unique_list(list(case.get("symptomTags") or []), tags)
    if queries_used:
        case["queriesUsed"] = _append_unique_list(list(case.get("queriesUsed") or []), queries_used)
    if objects_used:
        case["objectsUsed"] = _append_unique_list(list(case.get("objectsUsed") or []), objects_used)
    if methods_applied:
        case["methodsApplied"] = _append_unique_list(list(case.get("methodsApplied") or []), methods_applied)
    if sources_used:
        case["sourcesUsed"] = _append_unique_list(list(case.get("sourcesUsed") or []), sources_used)

    if status.strip():
        case["status"] = status.strip()
    elif not case.get("status"):
        case["status"] = "draft"

    case["updatedAt"] = _now_iso()
    case["verifiedByAnalyst"] = verified_by_analyst

    if not case.get("correctSolution") and str(case.get("status", "")).lower() == "final":
        raise ValueError("correct_solution обязателен для status=final.")

    directory = cases_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    case_path = directory / f"{case_id}.json"
    case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

    preview = str(case.get("correctSolution") or case.get("contextSummary") or case.get("symptom", ""))[:240]
    index_item = {
        "id": case_id,
        "createdAt": created_at,
        "updatedAt": case.get("updatedAt"),
        "configurationName": case.get("configurationName", ""),
        "configurationVersion": case.get("configurationVersion", ""),
        "symptom": str(case.get("symptom", "")),
        "symptomTags": case.get("symptomTags", []),
        "status": case.get("status", "draft"),
        "correctSolutionPreview": preview,
    }
    index_items = [item for item in load_index(root) if str(item.get("id")) != case_id]
    index_items.insert(0, index_item)
    save_index(root, index_items)
    return case


def get_case(root: Path, case_id: str) -> dict[str, Any]:
    case_id = case_id.strip()
    if not case_id:
        raise ValueError("case_id обязателен.")

    case_path = cases_dir(root) / f"{case_id}.json"
    if not case_path.is_file():
        raise ValueError(f"Кейс '{case_id}' не найден.")

    data = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Некорректный формат кейса.")
    return data


def _score_case(case: dict[str, Any], query_tokens: set[str], configuration_name: str) -> float:
    haystack = " ".join(
        [
            str(case.get("symptom", "")),
            str(case.get("correctSolution", "")),
            str(case.get("wrongApproach", "")),
            str(case.get("contextSummary", "")),
            str(case.get("investigationPath", "")),
            str(case.get("hypotheses", "")),
            " ".join(case.get("symptomTags", []) or []),
            " ".join(case.get("objectsUsed", []) or []),
            " ".join(case.get("methodsApplied", []) or []),
            " ".join(case.get("sourcesUsed", []) or []),
        ]
    )
    case_tokens = _tokenize(haystack)
    if not query_tokens:
        return 0.0

    overlap = len(query_tokens & case_tokens)
    score = float(overlap)

    config = str(case.get("configurationName") or "").strip().lower()
    if configuration_name and config and configuration_name.lower() == config:
        score += 2.0

    return score


def _rank_local_cases(
    root: Path,
    query_tokens: set[str],
    configuration_name: str,
) -> list[tuple[float, dict[str, Any]]]:
    ranked: list[tuple[float, dict[str, Any]]] = []

    for item in load_index(root):
        case_id = str(item.get("id") or "").strip()
        if not case_id:
            continue
        try:
            case = get_case(root, case_id)
        except (ValueError, RuntimeError, json.JSONDecodeError):
            continue

        score = _score_case(case, query_tokens, configuration_name)
        if score <= 0:
            continue
        case["source"] = "json"
        ranked.append((score, case))

    return ranked


def search_cases(
    root: Path,
    query: str,
    *,
    configuration_name: str = "",
    database_name: str = "",
    project_name: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("query обязателен.")

    if limit < 1:
        limit = 1
    if limit > 20:
        limit = 20

    query_tokens = _tokenize(query)
    ranked = _rank_local_cases(root, query_tokens, configuration_name)

    try:
        from obsidian_vault import search_obsidian_cases

        for case in search_obsidian_cases(
            root,
            query,
            configuration_name=configuration_name,
            database_name=database_name or project_name,
            limit=limit * 2,
        ):
            score = _score_case(case, query_tokens, configuration_name)
            if score > 0:
                ranked.append((score, case))
    except ImportError:
        pass

    seen_ids: set[str] = set()
    unique_ranked: list[tuple[float, dict[str, Any]]] = []
    for score, case in sorted(ranked, key=lambda pair: pair[0], reverse=True):
        case_id = str(case.get("id") or "")
        dedupe_key = case_id or str(case.get("obsidianPath", ""))
        if dedupe_key and dedupe_key in seen_ids:
            continue
        if dedupe_key:
            seen_ids.add(dedupe_key)
        unique_ranked.append((score, case))

    matches = [case for _, case in unique_ranked[:limit]]

    return {
        "query": query,
        "configurationName": configuration_name,
        "databaseName": database_name or project_name,
        "count": len(matches),
        "matches": matches,
        "mustReviewBeforeInvestigation": len(matches) > 0,
    }
