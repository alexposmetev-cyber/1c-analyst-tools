"""Регистрация XML-исходников конфигурации и поиск/чтение BSL без COM."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCES_FILENAME = ".onec-config-sources.json"

METADATA_FOLDER_MAP: dict[str, str] = {
    "Справочник": "Catalogs",
    "Документ": "Documents",
    "ОбщийМодуль": "CommonModules",
    "РегистрСведений": "InformationRegisters",
    "РегистрНакопления": "AccumulationRegisters",
    "Обработка": "DataProcessors",
    "Отчет": "Reports",
    "Перечисление": "Enums",
    "Константа": "Constants",
    "ПланВидовХарактеристик": "ChartsOfCharacteristicTypes",
    "ПланСчетов": "ChartsOfAccounts",
    "ПланОбмена": "ExchangePlans",
    "БизнесПроцесс": "BusinessProcesses",
    "Задача": "Tasks",
}

MODULE_PART_FILES = {
    "manager": "ManagerModule.bsl",
    "object": "ObjectModule.bsl",
    "module": "Module.bsl",
}


def _sources_path(root: Path) -> Path:
    return root / SOURCES_FILENAME


def _load_store(root: Path) -> dict[str, Any]:
    path = _sources_path(root)
    if not path.is_file():
        return {"active_source_id": "", "sources": []}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active_source_id": "", "sources": []}

    if not isinstance(data, dict):
        return {"active_source_id": "", "sources": []}

    sources = data.get("sources")
    if not isinstance(sources, list):
        sources = []

    return {
        "active_source_id": str(data.get("active_source_id") or "").strip(),
        "sources": [item for item in sources if isinstance(item, dict)],
    }


def _save_store(root: Path, store: dict[str, Any]) -> None:
    path = _sources_path(root)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_path(value: str) -> Path:
    return Path(value.strip()).expanduser().resolve()


def is_valid_config_sources_path(path: Path) -> bool:
    if not path.is_dir():
        return False

    if (path / "Configuration.xml").is_file():
        return True

    for folder in (
        "Catalogs",
        "Documents",
        "CommonModules",
        "DataProcessors",
        "Reports",
    ):
        if (path / folder).is_dir():
            return True

    return False


def count_bsl_files(path: Path) -> int:
    return sum(1 for _ in path.rglob("*.bsl"))


def count_xml_files(path: Path) -> int:
    return sum(1 for _ in path.rglob("*.xml"))


def parse_full_name(full_name: str) -> tuple[str, str]:
    text = full_name.strip()
    match = re.match(r"^([^.]+)\.(.+)$", text)
    if not match:
        raise ValueError(
            f"Некорректное полное имя: {full_name}. Ожидается, например, Документ.ЗаказКлиента."
        )
    return match.group(1), match.group(2)


def module_relative_path(full_name: str, module_part: str = "manager") -> str:
    type_prefix, object_name = parse_full_name(full_name)
    folder = METADATA_FOLDER_MAP.get(type_prefix)
    if not folder:
        raise ValueError(f"Тип метаданных не поддерживается: {type_prefix}")

    part = module_part.strip().lower()
    if part not in MODULE_PART_FILES:
        raise ValueError("module_part: manager, object или module.")

    file_name = MODULE_PART_FILES[part]
    if type_prefix == "ОбщийМодуль":
        file_name = "Module.bsl"

    return str(Path(folder) / object_name / "Ext" / file_name)


def find_module_file(sources_root: Path, full_name: str, module_part: str = "manager") -> Path | None:
    relative = module_relative_path(full_name, module_part)
    direct = sources_root / relative
    if direct.is_file():
        return direct

    _, object_name = parse_full_name(full_name)
    pattern = f"*{object_name}*"
    for candidate in sources_root.rglob("*.bsl"):
        if object_name.lower() in candidate.name.lower() or object_name.lower() in str(candidate).lower():
            name_lower = candidate.name.lower()
            if part_wanted := MODULE_PART_FILES.get(module_part.strip().lower(), ""):
                if name_lower == part_wanted.lower():
                    return candidate

    for candidate in sources_root.rglob(pattern):
        if candidate.suffix.lower() == ".bsl":
            return candidate

    return None


def register_source(
    root: Path,
    sources_path: str,
    *,
    label: str = "",
    configuration_name: str = "",
    target_key: str = "",
    origin: str = "register",
    set_active: bool = True,
) -> dict[str, Any]:
    path = _normalize_path(sources_path)
    if not is_valid_config_sources_path(path):
        raise ValueError(
            f"Каталог не похож на выгрузку конфигурации 1С: {path}. "
            "Ожидается Configuration.xml или подкаталоги Catalogs/Documents/CommonModules."
        )

    store = _load_store(root)
    normalized = str(path)
    existing = next(
        (item for item in store["sources"] if str(item.get("path", "")).lower() == normalized.lower()),
        None,
    )

    if existing:
        source = existing
        source["label"] = label.strip() or source.get("label", "")
        source["configuration_name"] = configuration_name.strip() or source.get("configuration_name", "")
        source["target_key"] = target_key.strip() or source.get("target_key", "")
        source["origin"] = origin or source.get("origin", "register")
        source["bsl_count"] = count_bsl_files(path)
        source["xml_count"] = count_xml_files(path)
        source["updated_at"] = _now_iso()
    else:
        source = {
            "id": uuid.uuid4().hex[:12],
            "path": normalized,
            "label": label.strip() or path.name,
            "configuration_name": configuration_name.strip(),
            "target_key": target_key.strip(),
            "origin": origin,
            "registered_at": _now_iso(),
            "updated_at": _now_iso(),
            "bsl_count": count_bsl_files(path),
            "xml_count": count_xml_files(path),
        }
        store["sources"].append(source)

    if set_active:
        store["active_source_id"] = str(source["id"])

    _save_store(root, store)
    return source


def unregister_source(root: Path, source_id: str = "") -> dict[str, Any]:
    store = _load_store(root)
    source_id = source_id.strip()

    if not source_id:
        store = {"active_source_id": "", "sources": []}
        _save_store(root, store)
        return {"removed": "all", "count": 0}

    before = len(store["sources"])
    store["sources"] = [item for item in store["sources"] if str(item.get("id", "")) != source_id]
    removed = before - len(store["sources"])

    if store.get("active_source_id") == source_id:
        store["active_source_id"] = str(store["sources"][0]["id"]) if store["sources"] else ""

    _save_store(root, store)
    return {"removed": source_id, "count": removed}


def resolve_active_source(root: Path, source_id: str = "") -> dict[str, Any] | None:
    store = _load_store(root)
    query = source_id.strip() or str(store.get("active_source_id") or "").strip()
    if not query:
        if len(store["sources"]) == 1:
            return store["sources"][0]
        return None

    for item in store["sources"]:
        if str(item.get("id", "")) == query:
            return item

    return None


def sources_status(root: Path) -> dict[str, Any]:
    store = _load_store(root)
    active = resolve_active_source(root)
    payload: dict[str, Any] = {
        "registered_count": len(store["sources"]),
        "active_source_id": store.get("active_source_id", ""),
        "sources": [],
        "agent_action": (
            "AGENT_ACTION: сначала спросите пользователя — есть ли уже выгруженная конфигурация в файлах "
            "(Git, каталог разработки, XML). Если да — onec_config_sources_register(path=...). "
            "Если нет — onec_dump_config (нужен onec_connect) или пользователь выгружает вручную."
        ),
    }

    for item in store["sources"]:
        path = Path(str(item.get("path", "")))
        payload["sources"].append(
            {
                "id": item.get("id", ""),
                "label": item.get("label", ""),
                "path": str(path),
                "configuration_name": item.get("configuration_name", ""),
                "target_key": item.get("target_key", ""),
                "origin": item.get("origin", ""),
                "bsl_count": item.get("bsl_count", 0),
                "xml_count": item.get("xml_count", 0),
                "exists": path.is_dir(),
            }
        )

    if active:
        payload["active"] = {
            "id": active.get("id", ""),
            "label": active.get("label", ""),
            "path": active.get("path", ""),
            "bsl_count": active.get("bsl_count", 0),
        }
    else:
        payload["active"] = None

    return payload


def read_module_from_sources(
    root: Path,
    full_name: str,
    module_part: str = "manager",
    *,
    source_id: str = "",
    max_lines: int = 400,
) -> dict[str, Any]:
    source = resolve_active_source(root, source_id)
    if not source:
        raise RuntimeError(
            "Источник XML не зарегистрирован. onec_config_sources_register(path=...) "
            "или onec_dump_config после connect."
        )

    sources_root = Path(str(source["path"]))
    if not sources_root.is_dir():
        raise RuntimeError(f"Каталог исходников не найден: {sources_root}")

    module_file = find_module_file(sources_root, full_name, module_part)
    if not module_file:
        raise RuntimeError(
            f"Модуль не найден в {sources_root} для {full_name} ({module_part}). "
            "Проверьте имя объекта или выполните partial dump."
        )

    if max_lines < 50:
        max_lines = 50
    if max_lines > 2000:
        max_lines = 2000

    try:
        lines = module_file.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = module_file.read_text(encoding="utf-8-sig").splitlines()

    total = len(lines)
    truncated = total > max_lines
    slice_lines = lines[:max_lines] if truncated else lines

    return {
        "status": "ok",
        "source_id": source.get("id", ""),
        "sources_path": str(sources_root),
        "full_name": full_name.strip(),
        "module_part": module_part.strip().lower(),
        "file_path": str(module_file),
        "relative_path": str(module_file.relative_to(sources_root)),
        "line_count": total,
        "truncated": truncated,
        "from_cache": True,
        "text": "\n".join(slice_lines),
    }


def search_code_in_sources(
    root: Path,
    query: str,
    *,
    source_id: str = "",
    limit: int = 15,
) -> dict[str, Any]:
    source = resolve_active_source(root, source_id)
    if not source:
        raise RuntimeError(
            "Источник XML не зарегистрирован. Сначала onec_config_sources_register или onec_dump_config."
        )

    sources_root = Path(str(source["path"]))
    if not sources_root.is_dir():
        raise RuntimeError(f"Каталог исходников не найден: {sources_root}")

    query = query.strip()
    if not query:
        raise ValueError("Параметр query не может быть пустым.")

    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    tokens = [part.lower() for part in re.split(r"\s+", query) if part.strip()]
    matches: list[dict[str, Any]] = []

    for bsl_file in sorted(sources_root.rglob("*.bsl")):
        try:
            lines = bsl_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            try:
                lines = bsl_file.read_text(encoding="utf-8-sig").splitlines()
            except OSError:
                continue
        except OSError:
            continue

        for line_no, line in enumerate(lines, start=1):
            line_lower = line.lower()
            if all(token in line_lower for token in tokens):
                matches.append(
                    {
                        "file": str(bsl_file.relative_to(sources_root)),
                        "line": line_no,
                        "text": line.strip()[:300],
                    }
                )
                if len(matches) >= limit:
                    break
        if len(matches) >= limit:
            break

    return {
        "status": "ok",
        "source_id": source.get("id", ""),
        "sources_path": str(sources_root),
        "query": query,
        "match_count": len(matches),
        "matches": matches,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
