"""Библиотека метаданных конфигураций 1С: кэш, версии, публикация."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


def metadata_fingerprint(manifest: dict[str, Any]) -> str:
    name = str(manifest.get("configurationName") or "").strip()
    version = str(manifest.get("version") or "").strip() or "unknown"
    object_count = int(manifest.get("objectCount") or 0)
    return f"{name}|{version}|{object_count}"


def library_relative_path(manifest: dict[str, Any]) -> str:
    name = _safe_segment(str(manifest.get("configurationName") or "UnknownConfig"))
    version = _safe_segment(str(manifest.get("version") or "").strip() or "unknown")
    return f"metadata/library/{name}/{version}"


def resolve_cache_dir(root: Path, cache_relative: str | None) -> Path | None:
    if not cache_relative:
        return None

    normalized = cache_relative.replace("/", "\\").strip("\\")
    candidates = [
        root / normalized,
        root / "metadata" / "cache" / normalized,
    ]

    for candidate in candidates:
        if candidate.is_dir() and (candidate / "manifest.json").is_file():
            return candidate

    return None


def resolve_library_dir(root: Path, manifest: dict[str, Any]) -> Path:
    return root / Path(library_relative_path(manifest).replace("/", "\\"))


def load_manifest(cache_dir: Path) -> dict[str, Any] | None:
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.is_file():
        return None

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return data


def load_index(cache_dir: Path) -> list[dict[str, Any]]:
    index_path = cache_dir / "index.json"
    if not index_path.is_file():
        return []

    try:
        data = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []


def publish_metadata_to_library(root: Path, cache_dir: Path, manifest: dict[str, Any]) -> str:
    library_dir = resolve_library_dir(root, manifest)
    if library_dir.exists():
        shutil.rmtree(library_dir)
    shutil.copytree(cache_dir, library_dir)

    library_manifest = dict(manifest)
    library_manifest["libraryPath"] = library_relative_path(manifest)
    library_manifest["publishedFromCache"] = str(cache_dir)
    (library_dir / "manifest.json").write_text(
        json.dumps(library_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return library_relative_path(manifest)


def compare_metadata_session(
    session: dict[str, str],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    current_fp = metadata_fingerprint(manifest)
    session_fp = str(session.get("metadata_fingerprint") or "").strip()
    session_name = str(session.get("configuration_name") or "").strip()
    session_version = str(session.get("configuration_version") or "").strip()
    manifest_name = str(manifest.get("configurationName") or "").strip()
    manifest_version = str(manifest.get("version") or "").strip()

    reasons: list[str] = []
    if session_fp and session_fp != current_fp:
        reasons.append(
            f"отпечаток метаданных изменился: было {session_fp}, стало {current_fp}"
        )
    if session_name and manifest_name and session_name != manifest_name:
        reasons.append(
            f"конфигурация изменилась: было {session_name}, стало {manifest_name}"
        )
    if session_version and manifest_version and session_version != manifest_version:
        reasons.append(
            f"версия изменилась: было {session_version}, стало {manifest_version}"
        )

    return {
        "match": len(reasons) == 0,
        "stale": len(reasons) > 0,
        "reasons": reasons,
        "sessionFingerprint": session_fp,
        "currentFingerprint": current_fp,
        "configurationName": manifest_name,
        "version": manifest_version or "unknown",
    }


def metadata_status(
    root: Path,
    cache_relative: str | None,
    session: dict[str, str] | None = None,
) -> dict[str, Any]:
    cache_dir = resolve_cache_dir(root, cache_relative)
    if not cache_dir:
        return {"ready": False, "message": "Кэш метаданных не найден. Выполните onec-data_onec_connect."}

    manifest = load_manifest(cache_dir)
    if not manifest:
        return {"ready": False, "message": "manifest.json повреждён или отсутствует."}

    payload: dict[str, Any] = {
        "ready": True,
        "cachePath": manifest.get("cacheRelative") or str(cache_dir.relative_to(root)).replace("\\", "/"),
        "libraryPath": manifest.get("libraryPath") or library_relative_path(manifest),
        "configurationName": manifest.get("configurationName", ""),
        "configurationSynonym": manifest.get("configurationSynonym", ""),
        "version": manifest.get("version", "") or "unknown",
        "objectCount": manifest.get("objectCount", 0),
        "exportedAt": manifest.get("exportedAt", ""),
        "target": manifest.get("target", ""),
        "fingerprint": metadata_fingerprint(manifest),
    }

    if session:
        comparison = compare_metadata_session(session, manifest)
        payload["sessionMatch"] = comparison["match"]
        payload["stale"] = comparison["stale"]
        payload["staleReasons"] = comparison["reasons"]
        if comparison["stale"]:
            payload["ready"] = False
            payload["message"] = (
                "Метаданные не совпадают с текущей сессией. "
                "Вызовите onec-data_onec_refresh_metadata(force=true)."
            )

    return payload


def ensure_metadata_ready(
    root: Path,
    session: dict[str, str],
) -> dict[str, Any]:
    cache_relative = session.get("metadata_cache", "").strip() or None
    status = metadata_status(root, cache_relative, session)
    if not status.get("ready"):
        raise RuntimeError(status.get("message") or "Кэш метаданных не готов.")
    return status


def metadata_search(
    root: Path,
    cache_relative: str | None,
    query: str,
    limit: int = 20,
    session: dict[str, str] | None = None,
) -> dict[str, Any]:
    if session:
        ensure_metadata_ready(root, session)

    cache_dir = resolve_cache_dir(root, cache_relative)
    if not cache_dir:
        raise RuntimeError("Кэш метаданных не найден. Сначала выполните onec-data_onec_connect.")

    needle = query.strip().lower()
    if not needle:
        raise ValueError("Параметр query не может быть пустым.")

    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    matches: list[dict[str, Any]] = []
    for item in load_index(cache_dir):
        haystack = " ".join(
            [
                str(item.get("fullName", "")),
                str(item.get("name", "")),
                str(item.get("synonym", "")),
                str(item.get("type", "")),
            ]
        ).lower()
        if needle in haystack:
            matches.append(item)
        if len(matches) >= limit:
            break

    return {
        "query": query,
        "count": len(matches),
        "matches": matches,
    }


def metadata_object(
    root: Path,
    cache_relative: str | None,
    full_name: str,
    session: dict[str, str] | None = None,
) -> dict[str, Any]:
    if session:
        ensure_metadata_ready(root, session)

    cache_dir = resolve_cache_dir(root, cache_relative)
    if not cache_dir:
        raise RuntimeError("Кэш метаданных не найден. Сначала выполните onec-data_onec_connect.")

    name = full_name.strip()
    if not name:
        raise ValueError("Параметр full_name не может быть пустым.")

    object_path = cache_dir / "objects" / f"{name}.json"
    if not object_path.is_file():
        raise ValueError(f"Объект '{name}' не найден в кэше метаданных.")

    try:
        data = json.loads(object_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Не удалось прочитать карточку объекта: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Некорректный формат карточки объекта.")

    return data


def _target_matches_manifest(
    ib_path: str,
    server: str,
    ref: str,
    manifest: dict[str, Any],
) -> bool:
    target = str(manifest.get("target") or "").strip().lower()
    if not target:
        return False

    if ib_path:
        return target == ib_path.strip().lower()

    if server and ref:
        needle = f"{server.strip().lower()}/{ref.strip().lower()}"
        return needle in target or target == f"{server.strip().lower()} / {ref.strip().lower()}"

    return False


def find_metadata_cache_for_target(
    root: Path,
    *,
    info_base_path: str = "",
    server: str = "",
    ref: str = "",
) -> dict[str, Any] | None:
    """Ищет готовый кэш metadata/cache по полю target в manifest.json."""
    cache_root = root / "metadata" / "cache"
    if not cache_root.is_dir():
        return None

    for child in sorted(cache_root.iterdir()):
        if not child.is_dir():
            continue
        manifest = load_manifest(child)
        if not manifest:
            continue
        if _target_matches_manifest(info_base_path, server, ref, manifest):
            return manifest

    return None


def update_session_metadata_cache(session: dict[str, str], manifest: dict[str, Any]) -> dict[str, str]:
    updated = dict(session)
    cache_path = str(manifest.get("cacheRelative", "")).strip().replace("\\", "/")

    if cache_path:
        if not cache_path.startswith("metadata/cache/"):
            cache_path = f"metadata/cache/{cache_path.lstrip('/')}"
        updated["metadata_cache"] = cache_path

    updated["configuration_name"] = str(manifest.get("configurationName") or "").strip()
    updated["configuration_version"] = str(manifest.get("version") or "").strip() or "unknown"
    updated["metadata_fingerprint"] = metadata_fingerprint(manifest)
    updated["metadata_library"] = str(manifest.get("libraryPath") or library_relative_path(manifest)).strip()
    return updated


def _safe_segment(text: str) -> str:
    value = text.strip() or "unknown"
    value = re.sub(r"\s+", "_", value)
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    return value
