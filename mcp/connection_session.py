"""Сессия подключения к базе 1С для MCP (память + .onec-session.json)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SESSION_FILENAME = ".onec-session.json"


def _normalize_platform_major(version: str) -> str:
    text = (version or "").strip()
    if not text:
        return ""
    if text in ("8.3", "8.5"):
        return text
    if text.startswith("8.5."):
        return "8.5"
    if text.startswith("8.3."):
        return "8.3"
    return text


def _session_path(root: Path) -> Path:
    return root / SESSION_FILENAME


def load_session(root: Path) -> dict[str, Any] | None:
    path = _session_path(root)
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    return _normalize_session(data)


def repair_session_file(root: Path) -> bool:
    """Нормализует .onec-session.json (platform_version -> 8.3/8.5). Возвращает True, если файл изменён."""
    path = _session_path(root)
    if not path.is_file():
        return False

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(raw, dict):
        return False

    normalized = _normalize_session(raw)
    old_version = str(raw.get("platform_version") or raw.get("PlatformVersion") or "").strip()
    new_version = normalized.get("platform_version", "")
    if old_version == new_version:
        return False

    save_session(root, normalized)
    return True


def save_session(root: Path, session: dict[str, Any]) -> None:
    path = _session_path(root)
    payload = _normalize_session(session)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_session(root: Path) -> None:
    path = _session_path(root)
    if path.is_file():
        path.unlink()


def resolve_connection(root: Path, memory_session: dict[str, Any] | None) -> dict[str, str] | None:
    candidates: list[dict[str, Any] | None] = [
        memory_session,
        load_session(root),
        _connection_from_env(),
    ]

    for item in candidates:
        if not item:
            continue
        normalized = _normalize_session(item)
        if _is_complete(normalized):
            return normalized

    return None


def connection_target_key(connection: dict[str, str]) -> str:
    ib_path = connection.get("info_base_path", "").strip().lower()
    if ib_path:
        return f"file:{ib_path}"

    server = connection.get("server", "").strip().lower()
    ref = connection.get("ref", "").strip().lower()
    return f"server:{server}/{ref}"


def targets_equal(left: dict[str, str], right: dict[str, str]) -> bool:
    return connection_target_key(left) == connection_target_key(right)


def _connection_from_env() -> dict[str, str] | None:
    ib_path = os.environ.get("ONEC_IB_PATH", "").strip()
    server = os.environ.get("ONEC_SERVER", "").strip()
    ref = os.environ.get("ONEC_REF", "").strip()
    user = os.environ.get("ONEC_USER", "").strip()

    if not user:
        return None

    if ib_path:
        return {
            "info_base_path": ib_path,
            "server": "",
            "ref": "",
            "user": user,
            "password": os.environ.get("ONEC_PASSWORD", ""),
            "platform_path": os.environ.get("ONEC_PLATFORM_PATH", "").strip(),
            "platform_version": _normalize_platform_major(
            os.environ.get("ONEC_PLATFORM_VERSION", "").strip()
        ),
            "metadata_cache": "",
        }

    if server and ref:
        return {
            "info_base_path": "",
            "server": server,
            "ref": ref,
            "user": user,
            "password": os.environ.get("ONEC_PASSWORD", ""),
            "platform_path": os.environ.get("ONEC_PLATFORM_PATH", "").strip(),
            "platform_version": _normalize_platform_major(
            os.environ.get("ONEC_PLATFORM_VERSION", "").strip()
        ),
            "metadata_cache": "",
        }

    return None


def build_connection_args(
    connection: dict[str, str],
    *,
    platform_version: str = "",
    include_prefer_version: bool = False,
) -> list[str]:
    args: list[str] = []

    ib_path = connection.get("info_base_path", "").strip()
    server = connection.get("server", "").strip()
    ref = connection.get("ref", "").strip()
    user = connection.get("user", "").strip()
    password = connection.get("password", "")

    if ib_path:
        args.extend(["-InfoBasePath", ib_path])
    elif server and ref:
        args.extend(["-Server", server, "-Ref", ref])
    else:
        raise RuntimeError(
            "Не задано подключение к базе. Вызовите onec_connect "
            "(файловая база: info_base_path; серверная: server + ref)."
        )

    args.extend(["-User", user])
    if password:
        args.extend(["-Password", password])

    platform_path = connection.get("platform_path", "").strip()
    if platform_path:
        args.extend(["-PlatformPath", platform_path])

    prefer_version = ""
    if include_prefer_version:
        prefer_version = _normalize_platform_major(
            platform_version.strip() or connection.get("platform_version", "").strip()
        )
    if prefer_version:
        args.extend(["-PreferPlatformVersion", prefer_version])

    return args


def public_view(connection: dict[str, str]) -> dict[str, str]:
    ib_path = connection.get("info_base_path", "").strip()
    server = connection.get("server", "").strip()
    ref = connection.get("ref", "").strip()

    if ib_path:
        target = ib_path
        target_type = "file"
    elif server and ref:
        target = f"{server} / {ref}"
        target_type = "server"
    else:
        target = ""
        target_type = "unknown"

    return {
        "target_type": target_type,
        "target": target,
        "target_key": connection_target_key(connection),
        "user": connection.get("user", ""),
        "platform_version": connection.get("platform_version", ""),
        "connected": "false",
    }


def _normalize_session(data: dict[str, Any]) -> dict[str, str]:
    return {
        "info_base_path": str(data.get("info_base_path") or data.get("InfoBasePath") or "").strip(),
        "server": str(data.get("server") or data.get("Server") or "").strip(),
        "ref": str(data.get("ref") or data.get("Ref") or "").strip(),
        "user": str(data.get("user") or data.get("User") or "").strip(),
        "password": str(data.get("password") or data.get("Password") or ""),
        "platform_path": str(data.get("platform_path") or data.get("PlatformPath") or "").strip(),
        "platform_version": _normalize_platform_major(
            str(
                data.get("platform_version")
                or data.get("PlatformVersion")
                or data.get("prefer_platform_version")
                or ""
            )
        ),
        "metadata_cache": str(data.get("metadata_cache") or data.get("MetadataCache") or "").strip(),
        "configuration_name": str(
            data.get("configuration_name") or data.get("configurationName") or data.get("ConfigurationName") or ""
        ).strip(),
        "configuration_version": str(
            data.get("configuration_version")
            or data.get("configurationVersion")
            or data.get("ConfigurationVersion")
            or ""
        ).strip(),
        "metadata_fingerprint": str(
            data.get("metadata_fingerprint") or data.get("metadataFingerprint") or ""
        ).strip(),
        "metadata_library": str(
            data.get("metadata_library") or data.get("metadataLibrary") or ""
        ).strip(),
        "info_base_display_name": str(
            data.get("info_base_display_name")
            or data.get("info_base_name")
            or data.get("display_name")
            or data.get("DisplayName")
            or ""
        ).strip(),
        "obsidian_database": str(
            data.get("obsidian_database") or data.get("obsidianDatabase") or ""
        ).strip(),
        "obsidian_project": str(
            data.get("obsidian_project") or data.get("project_name") or data.get("obsidianProject") or ""
        ).strip(),
        "obsidian_extension": str(
            data.get("obsidian_extension")
            or data.get("extension_name")
            or data.get("obsidianExtension")
            or ""
        ).strip(),
    }


def parse_connect_string(connect: str) -> dict[str, str]:
    """Разбирает строку Connect= из ibases.v8i или готовую COM-строку подключения."""
    result = {
        "info_base_path": "",
        "server": "",
        "ref": "",
        "user": "",
        "password": "",
    }

    text = connect.strip()
    if not text:
        return result

    file_match = re.search(r'File="([^"]+)"', text, re.IGNORECASE)
    if file_match:
        result["info_base_path"] = file_match.group(1)

    server_match = re.search(r'Srvr="([^"]+)"', text, re.IGNORECASE)
    if server_match:
        result["server"] = server_match.group(1)

    ref_match = re.search(r'Ref="([^"]+)"', text, re.IGNORECASE)
    if ref_match:
        result["ref"] = ref_match.group(1)

    usr_match = re.search(r'Usr="([^"]*)"', text, re.IGNORECASE)
    if usr_match:
        result["user"] = usr_match.group(1)

    pwd_match = re.search(r'Pwd="([^"]*)"', text, re.IGNORECASE)
    if pwd_match:
        result["password"] = pwd_match.group(1)

    return result


def normalize_info_base_path(value: str) -> str:
    """Путь к каталогу ИБ без префикса File= и хвостовой «;»."""
    text = value.strip().strip('"').strip("'")
    if not text:
        return ""

    if re.search(r'File="|Srvr="|Ref="|Usr="|Pwd=', text, re.IGNORECASE):
        parsed = parse_connect_string(text)
        return parsed.get("info_base_path", "").strip()

    if text.lower().startswith("file="):
        match = re.search(r'file="?([^";]+)"?', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return text.rstrip(";").strip()


def merge_connect_inputs(
    *,
    info_base_path: str = "",
    info_base_name: str = "",
    server: str = "",
    ref: str = "",
    user: str = "",
    password: str = "",
    connection_string: str = "",
) -> dict[str, str]:
    """Собирает параметры connect из полей MCP (в т.ч. если агент передал File=... целиком)."""
    connection_string = connection_string.strip()
    info_base_path = normalize_info_base_path(info_base_path)
    server = server.strip()
    ref = ref.strip()
    user = user.strip()
    password = password

    if connection_string:
        parsed = parse_connect_string(connection_string)
        if not info_base_path:
            info_base_path = parsed.get("info_base_path", "").strip()
        if not server:
            server = parsed.get("server", "").strip()
        if not ref:
            ref = parsed.get("ref", "").strip()
        if not user:
            user = parsed.get("user", "").strip()
        if password == "" and parsed.get("password"):
            password = parsed.get("password", "")

    return {
        "info_base_path": info_base_path,
        "info_base_name": info_base_name.strip(),
        "server": server,
        "ref": ref,
        "user": user,
        "password": password,
    }


def resolve_base_from_list(bases: list[dict[str, Any]], name: str) -> dict[str, str]:
    query = name.strip()
    if not query:
        raise ValueError("Имя базы не может быть пустым.")

    if query.isdigit():
        index = int(query) - 1
        if index < 0 or index >= len(bases):
            raise ValueError(f"Номер базы {query} вне диапазона 1..{len(bases)}.")
        selected = bases[index]
        connect = str(selected.get("connect") or selected.get("Connect") or "")
        parsed = parse_connect_string(connect)
        parsed["display_name"] = str(selected.get("name") or selected.get("Name") or "")
        return parsed

    query_lower = query.lower()
    for base in bases:
        display_name = str(base.get("name") or base.get("Name") or "")
        if display_name.lower() == query_lower:
            connect = str(base.get("connect") or base.get("Connect") or "")
            parsed = parse_connect_string(connect)
            parsed["display_name"] = display_name
            return parsed

    for base in bases:
        display_name = str(base.get("name") or base.get("Name") or "")
        if query_lower in display_name.lower():
            connect = str(base.get("connect") or base.get("Connect") or "")
            parsed = parse_connect_string(connect)
            parsed["display_name"] = display_name
            return parsed

    available = "; ".join(str(b.get("name") or b.get("Name") or "") for b in bases)
    raise ValueError(f"База '{name}' не найдена. Доступные: {available}")


def _is_complete(connection: dict[str, str]) -> bool:
    user = connection.get("user", "").strip()
    ib_path = connection.get("info_base_path", "").strip()
    server = connection.get("server", "").strip()
    ref = connection.get("ref", "").strip()

    if not user:
        return False

    if ib_path:
        return True

    return bool(server and ref)
