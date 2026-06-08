"""Запись артефактов аналитика в Obsidian vault (кейсы, ЛТ, сессии)."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def workspace_root(analyst_root: Path) -> Path:
    return analyst_root.parent


VAULT_DIR_NAME = "Obsidian"
LEGACY_VAULT_NAMES = ("Obsidian", "obsidian")


def resolve_vault_root(analyst_root: Path, *, create: bool = True) -> Path:
    """Корень vault: 1c-analyst-tools/.Obsidian (создаётся при отсутствии)."""
    env_path = os.environ.get("ONEC_OBSIDIAN_VAULT", "").strip()
    if env_path:
        vault = Path(env_path)
    else:
        vault = analyst_root / VAULT_DIR_NAME

    if create:
        vault.mkdir(parents=True, exist_ok=True)
        _ensure_vault_index(vault)

    return vault


def legacy_vault_roots(analyst_root: Path) -> list[Path]:
    """Старые каталоги Obsidian/ — только для поиска кейсов."""
    workspace = workspace_root(analyst_root)
    primary = resolve_vault_root(analyst_root, create=False)
    roots: list[Path] = []
    for name in LEGACY_VAULT_NAMES:
        candidate = workspace / name
        if candidate.is_dir() and candidate.resolve() != primary.resolve():
            roots.append(candidate)
    return roots


def all_search_vault_roots(analyst_root: Path) -> list[Path]:
    roots = [resolve_vault_root(analyst_root, create=False)]
    if not roots[0].is_dir():
        roots = []
    roots.extend(legacy_vault_roots(analyst_root))
    return roots


def default_database_name(analyst_root: Path) -> str:
    return os.environ.get("ONEC_OBSIDIAN_DATABASE", "").strip() or "offline"


def resolve_database_name(
    session: dict[str, str] | None = None,
    *,
    database_name: str = "",
    analyst_root: Path | None = None,
) -> str:
    """Имя папки ИБ под .Obsidian (из сессии connect, явного параметра или offline)."""
    explicit = database_name.strip()
    if explicit:
        return _safe_segment(explicit, "offline")

    session = session or {}
    stored = str(session.get("obsidian_database") or "").strip()
    if stored:
        return _safe_segment(stored, "offline")

    display = str(session.get("info_base_display_name") or session.get("info_base_name") or "").strip()
    if display:
        return _safe_segment(display, "offline")

    ib_path = str(session.get("info_base_path") or "").strip()
    if ib_path:
        return _safe_segment(Path(ib_path).name, "offline")

    server = str(session.get("server") or "").strip()
    ref = str(session.get("ref") or "").strip()
    if server and ref:
        return _safe_segment(f"{server}_{ref}", "offline")

    if analyst_root:
        env_default = default_database_name(analyst_root)
        if env_default != "offline":
            return _safe_segment(env_default, "offline")

    return "offline"


def _ensure_vault_index(vault_root: Path) -> None:
    index_path = vault_root / "_Index.md"
    if index_path.is_file():
        return

    index_path.write_text(
        "\n".join(
            [
                "# Архив аналитика 1С",
                "",
                "Каталоги по **информационным базам** (имя из `onec_connect` или каталога ИБ).",
                "",
                "Расположение: `1c-analyst-tools/.Obsidian/`",
                "",
                "```",
                "1c-analyst-tools/.Obsidian/{ИмяБазы}/",
                "  Cases/",
                "  Requirements/",
                "  Sessions/",
                "  Справочники/",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


HANDBOOKS_FOLDER = "Справочники"
DATABASE_SUBFOLDERS = ("Cases", "Requirements", "Sessions", HANDBOOKS_FOLDER)


def ensure_database_folders(vault_root: Path, database_name: str) -> Path:
    """Создаёт .Obsidian/{база}/Cases|Requirements|Sessions|Справочники."""
    db_root = vault_root / database_name
    for subfolder in DATABASE_SUBFOLDERS:
        (db_root / subfolder).mkdir(parents=True, exist_ok=True)
    return db_root


def _database_root(vault_root: Path, context: dict[str, str]) -> Path:
    return vault_root / context["database_name"]


def _tokenize_search(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_\.]+", text.lower())
    return {word for word in words if len(word) >= 3}


def _score_text(query_tokens: set[str], haystack: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize_search(haystack)
    return float(len(query_tokens & text_tokens))


def _search_markdown_folder(
    folder: Path,
    query: str,
    *,
    limit: int = 5,
    vault_root: Path | None = None,
) -> list[dict[str, Any]]:
    if not folder.is_dir():
        return []

    query_tokens = _tokenize_search(query)
    if not query_tokens:
        return []

    ranked: list[tuple[float, dict[str, Any]]] = []
    for md_path in sorted(folder.glob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue

        score = _score_text(query_tokens, text)
        if score <= 0:
            continue

        item: dict[str, Any] = {
            "file": md_path.name,
            "score": score,
            "preview": text[:400].replace("\n", " "),
        }
        if vault_root:
            item["relativePath"] = md_path.relative_to(vault_root).as_posix()
        ranked.append((score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]


def search_handbooks(
    analyst_root: Path,
    query: str,
    *,
    database_name: str = "",
    session: dict[str, str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    context = resolve_context(
        database_name=database_name,
        session=session,
        analyst_root=analyst_root,
    )
    vault_root = resolve_vault_root(analyst_root)
    ensure_database_folders(vault_root, context["database_name"])
    folder = _database_root(vault_root, context) / HANDBOOKS_FOLDER

    matches = _search_markdown_folder(folder, query, limit=limit, vault_root=vault_root)
    return {
        "databaseName": context["database_name"],
        "configurationName": context["configuration_name"],
        "folder": f"{context['database_name']}/{HANDBOOKS_FOLDER}",
        "folderExists": folder.is_dir(),
        "hasHandbooks": len(matches) > 0,
        "count": len(matches),
        "matches": matches,
        "guidance": (
            "Если найдено — опирайтесь на типовой функционал из справочников; "
            "не смешивайте объекты другой конфигурации."
            if matches
            else "Справочники пусты или не найдены — контекст наполняется из ИТС/интернета/кода; "
            "при необходимости добавьте .md в папку Справочники."
        ),
    }


def search_similar_requirements(
    analyst_root: Path,
    query: str,
    *,
    database_name: str = "",
    session: dict[str, str] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    context = resolve_context(
        database_name=database_name,
        session=session,
        analyst_root=analyst_root,
    )
    vault_root = resolve_vault_root(analyst_root)
    folder = _database_root(vault_root, context) / "Requirements"
    matches = _search_markdown_folder(folder, query, limit=limit, vault_root=vault_root)

    return {
        "databaseName": context["database_name"],
        "count": len(matches),
        "matches": matches,
    }


def prepare_requirements_context(
    analyst_root: Path,
    task_description: str,
    *,
    configuration_name: str = "",
    database_name: str = "",
    session: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Контекст для ЛТ: кейсы, прошлые ЛТ, справочники; предупреждение о смешении конфигураций."""
    from case_library import search_cases

    task_description = task_description.strip()
    if not task_description:
        raise ValueError("task_description обязателен.")

    context = resolve_context(
        database_name=database_name,
        configuration_name=configuration_name,
        session=session,
        analyst_root=analyst_root,
    )

    config_for_search = configuration_name or context["configuration_name"]
    cases = search_cases(
        analyst_root,
        task_description,
        configuration_name=config_for_search,
        database_name=context["database_name"],
        limit=5,
    )
    handbooks = search_handbooks(
        analyst_root,
        task_description,
        database_name=context["database_name"],
        session=session,
        limit=5,
    )
    past_lt = search_similar_requirements(
        analyst_root,
        task_description,
        database_name=context["database_name"],
        session=session,
        limit=5,
    )

    similar_found = (
        cases.get("count", 0) > 0
        or past_lt.get("count", 0) > 0
        or handbooks.get("hasHandbooks", False)
    )

    return {
        "databaseName": context["database_name"],
        "configurationName": config_for_search,
        "similarWorkFound": similar_found,
        "cases": cases,
        "pastRequirements": past_lt,
        "handbooks": handbooks,
        "configurationIsolation": (
            "КРИТИЧНО: не переносите объекты, регистры и механизмы из другой конфигурации. "
            f"Текущий контекст: база «{context['database_name']}», конфигурация «{config_for_search}». "
            "ИТС/форумы/код — только для этой конфигурации."
        ),
        "nextSteps": [
            "1. Учесть найденные кейсы и прошлые ЛТ.",
            "2. Если есть Справочники — проверить типовой функционал.",
            "3. Если в Obsidian пусто — onec_its_search, затем интернет (БИТ → info.bitmedic.ru).",
            "4. Если нужна разработка — спросить путь к XML; onec_config_sources_register или onec_dump_config; "
            "onec_config_read_module (только эта база/каталог).",
        ],
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def slugify(text: str, max_len: int = 80) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\wа-яё0-9]+", "-", text, flags=re.IGNORECASE)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "note"
    return text[:max_len].strip("-") or "note"


def _safe_segment(name: str, fallback: str) -> str:
    segment = re.sub(r'[<>:"/\\|?*]', "-", name.strip())
    segment = segment.strip(". ")
    return segment or fallback


def resolve_context(
    *,
    database_name: str = "",
    project_name: str = "",
    configuration_name: str = "",
    extension_name: str = "",
    session: dict[str, str] | None = None,
    analyst_root: Path | None = None,
) -> dict[str, str]:
    session = session or {}

    database = resolve_database_name(
        session,
        database_name=database_name or project_name,
        analyst_root=analyst_root,
    )
    configuration = (
        configuration_name.strip()
        or str(session.get("configuration_name", "")).strip()
        or "Unknown"
    )
    extension = (
        extension_name.strip()
        or str(session.get("obsidian_extension") or session.get("extension_name") or "").strip()
        or ""
    )

    return {
        "database_name": database,
        "configuration_name": _safe_segment(configuration, "Unknown"),
        "extension_name": _safe_segment(extension, "") if extension else "",
        # обратная совместимость в frontmatter
        "project_name": database,
    }


def vault_segment_path(vault_root: Path, context: dict[str, str], subfolder: str) -> Path:
    db_root = vault_root / context["database_name"]
    return db_root / subfolder


def _wikilink_objects(objects: list[str]) -> list[str]:
    links: list[str] = []
    for obj in objects:
        obj = obj.strip()
        if not obj:
            continue
        if obj.startswith("[[") and obj.endswith("]]"):
            links.append(obj)
        elif "." in obj:
            links.append(f"[[{obj}]]")
        else:
            links.append(obj)
    return links


def _parse_frontmatter_yaml_block(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end < 0:
        return {}

    block = text[3:end].strip()
    result: dict[str, Any] = {}
    current_key = ""
    list_key = ""

    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and list_key:
            result.setdefault(list_key, [])
            if isinstance(result[list_key], list):
                result[list_key].append(line[4:].strip().strip('"'))
            continue
        match = re.match(r"^([a-zA-Z_]+):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        current_key = key
        if value == "":
            list_key = key
            result[key] = []
        else:
            list_key = ""
            result[key] = value.strip('"')

    return result


def _case_body_markdown(case: dict[str, Any]) -> str:
    symptom = str(case.get("symptom", "")).strip()
    wrong = str(case.get("wrongApproach") or case.get("wrong_approach") or "").strip()
    solution = str(case.get("correctSolution") or case.get("correct_solution") or "").strip()
    status = str(case.get("status") or "final").strip()

    lines = [
        f"# Кейс: {symptom[:120]}",
        "",
        f"*Статус: {status}* · "
        f"обновлено: {str(case.get('updatedAt') or case.get('createdAt') or '')[:19]}",
        "",
        "## Симптом",
        "",
        symptom or "—",
        "",
    ]

    context = str(case.get("contextSummary") or "").strip()
    if context:
        lines.extend(["## Контекст", "", context, ""])

    investigation = str(case.get("investigationPath") or "").strip()
    methods = case.get("methodsApplied") or []
    if investigation or methods:
        lines.extend(["## Ход расследования", ""])
        if investigation:
            lines.extend([investigation, ""])
        if methods:
            lines.append("### Применённые способы")
            lines.append("")
            for item in methods:
                lines.append(f"- {item}")
            lines.append("")

    hypotheses = str(case.get("hypotheses") or "").strip()
    if hypotheses:
        lines.extend(["## Гипотезы", "", hypotheses, ""])

    if wrong:
        lines.extend(["## Неверный путь", "", wrong, ""])

    lines.extend(["## Решение", "", solution or "*(уточняется)*", ""])

    sources = case.get("sourcesUsed") or []
    if sources:
        lines.extend(["## Источники", ""])
        for source in sources:
            lines.append(f"- {source}")
        lines.append("")

    objects = case.get("objectsUsed") or case.get("objects_used") or []
    if objects:
        lines.extend(["## Объекты метаданных", ""])
        for obj in objects:
            lines.append(f"- {obj}")
        lines.append("")

    queries = case.get("queriesUsed") or case.get("queries_used") or []
    if queries:
        lines.extend(["## Запросы к ИБ", ""])
        for query in queries:
            lines.append(f"- `{query}`")
        lines.append("")

    checklist = str(case.get("checklist") or "").strip()
    if checklist:
        lines.extend(["## Чек-лист для повторения", "", checklist, ""])

    chronology = case.get("chronology") or []
    if chronology:
        lines.extend(["## Хронология дополнений", ""])
        for entry in chronology:
            if not isinstance(entry, dict):
                continue
            at = str(entry.get("at", ""))[:19]
            text = str(entry.get("text", "")).strip()
            if text:
                lines.append(f"- **{at}** — {text}")
        lines.append("")

    return "\n".join(lines)


def build_case_markdown(case: dict[str, Any], context: dict[str, str]) -> str:
    case_id = str(case.get("id") or uuid.uuid4().hex[:12])
    objects = case.get("objectsUsed") or case.get("objects_used") or []
    tags = case.get("symptomTags") or case.get("tags") or []

    yaml_lines = [
        "---",
        f"id: {case_id}",
        f"createdAt: {case.get('createdAt') or _now_iso()}",
        f"databaseName: {context['database_name']}",
        f"configurationName: {context['configuration_name']}",
        f"extension: {context['extension_name'] or '—'}",
        f'symptom: "{_escape_yaml(str(case.get("symptom", "")))}"',
    ]

    if wrong := str(case.get("wrongApproach") or case.get("wrong_approach") or "").strip():
        yaml_lines.append(f'wrongApproach: "{_escape_yaml(wrong)}"')

    solution = str(case.get("correctSolution") or case.get("correct_solution") or "").strip()
    yaml_lines.append(f'correctSolution: "{_escape_yaml(solution)}"')

    if tags:
        yaml_lines.append("symptomTags:")
        for tag in tags:
            yaml_lines.append(f"  - {tag}")

    object_links = _wikilink_objects([str(o) for o in objects])
    if object_links:
        yaml_lines.append("objectsUsed:")
        for link in object_links:
            yaml_lines.append(f"  - {link}")

    status = str(case.get("status") or "final").strip()
    yaml_lines.append(f"status: {status}")
    if updated := str(case.get("updatedAt") or "").strip():
        yaml_lines.append(f"updatedAt: {updated}")

    yaml_lines.append("tags:")
    yaml_lines.append("  - 1c/case")
    yaml_lines.append(f"  - database/{context['database_name']}")
    if status == "draft":
        yaml_lines.append("  - 1c/case-draft")
    yaml_lines.append("---")
    yaml_lines.append("")
    yaml_lines.append(_case_body_markdown(case))
    return "\n".join(yaml_lines)


def _escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def find_case_note_path(
    analyst_root: Path,
    case_id: str,
    *,
    database_name: str = "",
    session: dict[str, str] | None = None,
) -> Path | None:
    case_id = case_id.strip()
    if not case_id:
        return None

    vault_root = resolve_vault_root(analyst_root)
    context = resolve_context(
        database_name=database_name,
        session=session,
        analyst_root=analyst_root,
    )
    folder = vault_segment_path(vault_root, context, "Cases")
    index_path = folder / "index.json"
    if index_path.is_file():
        try:
            items = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(items, list):
                for item in items:
                    if str(item.get("id")) == case_id:
                        name = str(item.get("file", "")).strip()
                        if name:
                            candidate = folder / name
                            if candidate.is_file():
                                return candidate
        except (OSError, json.JSONDecodeError):
            pass

    if folder.is_dir():
        for md_file in folder.glob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if f"id: {case_id}" in text[:800]:
                return md_file
    return None


def save_case_note(
    analyst_root: Path,
    case: dict[str, Any],
    *,
    database_name: str = "",
    project_name: str = "",
    configuration_name: str = "",
    extension_name: str = "",
    session: dict[str, str] | None = None,
    slug: str = "",
    existing_relative_path: str = "",
) -> dict[str, Any]:
    vault_root = resolve_vault_root(analyst_root)
    context = resolve_context(
        database_name=database_name or project_name,
        configuration_name=configuration_name or str(case.get("configurationName", "")),
        extension_name=extension_name,
        session=session,
        analyst_root=analyst_root,
    )
    ensure_database_folders(vault_root, context["database_name"])
    case_id = str(case.get("id") or uuid.uuid4().hex[:12])
    case["id"] = case_id

    folder = vault_segment_path(vault_root, context, "Cases")
    folder.mkdir(parents=True, exist_ok=True)

    file_path: Path | None = None
    if existing_relative_path.strip():
        candidate = vault_root / existing_relative_path.strip().replace("/", "\\")
        if candidate.is_file():
            file_path = candidate
    if file_path is None:
        file_path = find_case_note_path(
            analyst_root,
            case_id,
            database_name=context["database_name"],
            session=session,
        )
    if file_path is None:
        file_slug = slug.strip() or slugify(str(case.get("symptom", case_id)))
        file_path = folder / f"{file_slug}.md"
        if file_path.exists() and file_path.stem != file_slug:
            file_path = folder / f"{file_slug}-{case_id[:8]}.md"

    content = build_case_markdown(case, context)
    file_path.write_text(content, encoding="utf-8")
    _update_cases_index(folder, case, context, file_path)

    rel = file_path.relative_to(vault_root).as_posix()
    return {
        "saved": True,
        "vault_root": str(vault_root),
        "relative_path": rel,
        "absolute_path": str(file_path),
        "case_id": case_id,
        "context": context,
    }


def _update_cases_index(
    cases_folder: Path,
    case: dict[str, Any],
    context: dict[str, str],
    file_path: Path,
) -> None:
    index_path = cases_folder / "index.json"
    items: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items = [item for item in data if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            items = []

    case_id = str(case.get("id", ""))
    items = [item for item in items if str(item.get("id")) != case_id]
    items.insert(
        0,
        {
            "id": case_id,
            "createdAt": case.get("createdAt", _now_iso()),
            "databaseName": context["database_name"],
            "configurationName": context["configuration_name"],
            "extension": context["extension_name"],
            "symptom": str(case.get("symptom", ""))[:240],
            "file": file_path.name,
            "wikilink": f"[[{file_path.stem}]]",
        },
    )
    index_path.write_text(json.dumps(items[:200], ensure_ascii=False, indent=2), encoding="utf-8")


def save_requirements_note(
    analyst_root: Path,
    *,
    title: str,
    body_markdown: str,
    database_name: str = "",
    project_name: str = "",
    configuration_name: str = "",
    extension_name: str = "",
    session: dict[str, str] | None = None,
    phase: str = "draft",
    slug: str = "",
) -> dict[str, Any]:
    title = title.strip()
    body = body_markdown.strip()
    if not body:
        raise ValueError("body_markdown обязателен.")

    vault_root = resolve_vault_root(analyst_root)
    context = resolve_context(
        database_name=database_name or project_name,
        configuration_name=configuration_name,
        extension_name=extension_name,
        session=session,
        analyst_root=analyst_root,
    )
    ensure_database_folders(vault_root, context["database_name"])

    folder = vault_segment_path(vault_root, context, "Requirements")
    folder.mkdir(parents=True, exist_ok=True)

    file_slug = slug.strip() or slugify(title or "requirements")
    note_id = uuid.uuid4().hex[:12]
    file_path = folder / f"{_today()}-{file_slug}.md"
    if file_path.exists():
        file_path = folder / f"{_today()}-{file_slug}-{note_id[:6]}.md"

    header_title = title or "Лист требований"
    content = "\n".join(
        [
            "---",
            f"id: {note_id}",
            f"createdAt: {_now_iso()}",
            f"title: \"{_escape_yaml(header_title)}\"",
            f"phase: {phase}",
            f"databaseName: {context['database_name']}",
            f"configurationName: {context['configuration_name']}",
            "tags:",
            "  - 1c/requirements",
            f"  - database/{context['database_name']}",
            "---",
            "",
            f"# {header_title}",
            "",
            body,
            "",
        ]
    )
    file_path.write_text(content, encoding="utf-8")

    rel = file_path.relative_to(vault_root).as_posix()
    return {
        "saved": True,
        "vault_root": str(vault_root),
        "relative_path": rel,
        "absolute_path": str(file_path),
        "id": note_id,
        "context": context,
    }


def save_session_note(
    analyst_root: Path,
    *,
    summary: str,
    transcript_markdown: str = "",
    database_name: str = "",
    project_name: str = "",
    configuration_name: str = "",
    extension_name: str = "",
    session: dict[str, str] | None = None,
    mode: str = "",
    slug: str = "",
) -> dict[str, Any]:
    summary = summary.strip()
    if not summary:
        raise ValueError("summary обязателен.")

    vault_root = resolve_vault_root(analyst_root)
    context = resolve_context(
        database_name=database_name or project_name,
        configuration_name=configuration_name,
        extension_name=extension_name,
        session=session,
        analyst_root=analyst_root,
    )
    ensure_database_folders(vault_root, context["database_name"])

    folder = vault_segment_path(vault_root, context, "Sessions")
    folder.mkdir(parents=True, exist_ok=True)

    file_slug = slug.strip() or slugify(summary[:60])
    note_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    file_path = folder / f"{timestamp}-{file_slug}.md"

    lines = [
        "---",
        f"id: {note_id}",
        f"createdAt: {_now_iso()}",
        f"databaseName: {context['database_name']}",
        f"configurationName: {context['configuration_name']}",
    ]
    if mode.strip():
        lines.append(f"mode: {mode.strip()}")
    lines.extend(
        [
            "tags:",
            "  - 1c/session",
            f"  - database/{context['database_name']}",
            "---",
            "",
            f"# Сессия: {summary[:200]}",
            "",
            "## Кратко",
            "",
            summary,
            "",
        ]
    )
    if transcript_markdown.strip():
        lines.extend(["## История диалога", "", transcript_markdown.strip(), ""])

    file_path.write_text("\n".join(lines), encoding="utf-8")
    rel = file_path.relative_to(vault_root).as_posix()
    return {
        "saved": True,
        "vault_root": str(vault_root),
        "relative_path": rel,
        "absolute_path": str(file_path),
        "id": note_id,
        "context": context,
    }


def append_session_note(
    analyst_root: Path,
    *,
    section: str,
    content: str,
    session_note_path: str = "",
) -> dict[str, Any]:
    section = section.strip() or "Дополнение"
    content = content.strip()
    if not content:
        raise ValueError("content обязателен.")

    vault_root = resolve_vault_root(analyst_root)
    rel_path = session_note_path.strip().replace("\\", "/")
    if not rel_path:
        raise ValueError("session_note_path обязателен (relative_path из onec_obsidian_save_session).")

    file_path = vault_root / rel_path
    if not file_path.is_file():
        raise FileNotFoundError(f"Заметка сессии не найдена: {rel_path}")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = "\n".join(
        [
            "",
            f"## {section} ({timestamp})",
            "",
            content,
            "",
        ]
    )

    existing = file_path.read_text(encoding="utf-8")
    file_path.write_text(existing.rstrip() + block, encoding="utf-8")

    return {
        "appended": True,
        "relative_path": rel_path,
        "absolute_path": str(file_path),
        "section": section,
    }


def _load_obsidian_cases_from_root(vault_root: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if not vault_root.is_dir():
        return cases

    for md_path in vault_root.glob("**/Cases/*.md"):
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue

        meta = _parse_frontmatter_yaml_block(text)
        case_id = str(meta.get("id") or md_path.stem)
        cases.append(
            {
                "id": case_id,
                "createdAt": str(meta.get("createdAt", "")),
                "databaseName": str(
                    meta.get("databaseName") or meta.get("project") or ""
                ),
                "configurationName": str(meta.get("configurationName", "")),
                "configurationVersion": str(meta.get("configurationVersion", "unknown")),
                "symptom": str(meta.get("symptom", "")),
                "symptomTags": meta.get("symptomTags") if isinstance(meta.get("symptomTags"), list) else [],
                "wrongApproach": str(meta.get("wrongApproach", "")),
                "correctSolution": str(meta.get("correctSolution", "")),
                "objectsUsed": meta.get("objectsUsed") if isinstance(meta.get("objectsUsed"), list) else [],
                "queriesUsed": [],
                "verifiedByAnalyst": True,
                "source": "obsidian",
                "obsidianPath": md_path.relative_to(vault_root).as_posix(),
            }
        )

    return cases


def _load_obsidian_cases(analyst_root: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for vault_root in all_search_vault_roots(analyst_root):
        for case in _load_obsidian_cases_from_root(vault_root):
            path_key = str(case.get("obsidianPath", ""))
            if path_key and path_key in seen_paths:
                continue
            if path_key:
                seen_paths.add(path_key)
            cases.append(case)
    return cases


def search_obsidian_cases(
    analyst_root: Path,
    query: str,
    *,
    configuration_name: str = "",
    database_name: str = "",
    project_name: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    from case_library import _score_case, _tokenize

    filter_database = (database_name or project_name).strip()
    query_tokens = _tokenize(query.strip())
    if not query_tokens:
        return []

    ranked: list[tuple[float, dict[str, Any]]] = []
    for case in _load_obsidian_cases(analyst_root):
        if filter_database:
            case_db = str(
                case.get("databaseName") or case.get("project") or case.get("database_name") or ""
            )
            if case_db and case_db.lower() != filter_database.lower():
                continue
        score = _score_case(case, query_tokens, configuration_name)
        if score > 0:
            ranked.append((score, case))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [case for _, case in ranked[:limit]]


def vault_status(analyst_root: Path, session: dict[str, str] | None = None) -> dict[str, Any]:
    vault_root = resolve_vault_root(analyst_root)
    exists = vault_root.is_dir()
    case_count = len(_load_obsidian_cases(analyst_root)) if exists else 0

    databases: list[str] = []
    if exists:
        for child in vault_root.iterdir():
            if child.is_dir() and not child.name.startswith("."):
                databases.append(child.name)

    current_db = resolve_database_name(session, analyst_root=analyst_root)

    return {
        "vault_root": str(vault_root),
        "vault_exists": exists,
        "vault_created_on_demand": True,
        "analyst_tools_root": str(analyst_root),
        "workspace_root": str(workspace_root(analyst_root)),
        "current_database_folder": current_db,
        "obsidian_case_count": case_count,
        "databases_in_vault": sorted(databases)[:50],
        "legacy_vaults": [str(path) for path in legacy_vault_roots(analyst_root)],
        "structure": "1c-analyst-tools/.Obsidian/{ИмяБазы}/{Cases|Requirements|Sessions|Справочники}/",
        "env": {
            "ONEC_OBSIDIAN_VAULT": os.environ.get("ONEC_OBSIDIAN_VAULT", ""),
            "ONEC_OBSIDIAN_DATABASE": os.environ.get("ONEC_OBSIDIAN_DATABASE", ""),
        },
    }
