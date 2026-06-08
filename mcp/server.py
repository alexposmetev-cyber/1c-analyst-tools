#!/usr/bin/env python3
"""MCP-сервер для read-only доступа к данным 1С через Get-1CData.ps1."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from connection_session import (
    build_connection_args,
    clear_session,
    connection_target_key,
    merge_connect_inputs,
    normalize_info_base_path,
    public_view,
    repair_session_file,
    resolve_base_from_list,
    resolve_connection,
    save_session,
    targets_equal,
)
from connect_errors import agent_hint_for_error, classify_connect_error
from case_library import get_case, save_case, search_cases
from bitmedic_research import bitmedic_search_guidance
from investigation_tracker import (
    clear_tracker,
    load_tracker,
    register_investigation,
    tracker_status,
    update_tracker_paths,
)
from obsidian_vault import (
    append_session_note,
    prepare_requirements_context,
    resolve_context,
    resolve_database_name,
    save_case_note,
    save_requirements_note,
    save_session_note,
    search_handbooks,
    vault_status,
)
from metadata_cache import (
    find_metadata_cache_for_target,
    load_manifest,
    metadata_object,
    metadata_search,
    metadata_status,
    publish_metadata_to_library,
    resolve_cache_dir,
    update_session_metadata_cache,
)
from config_sources import (
    read_module_from_sources,
    register_source,
    search_code_in_sources,
    sources_status,
    unregister_source,
)
from session_context import reset_session_for_new_chat
from welcome import welcome_payload_json
from web_research import (
    clear_its_payload,
    configure_its_payload,
    fetch_its_payload,
    search_forums_payload,
    search_its_payload,
    web_research_status,
)

ROOT = Path(__file__).resolve().parent.parent
GET_DATA_SCRIPT = ROOT / "Get-1CData.ps1"

_powershell_exe: str | None = None


def _resolve_powershell_exe() -> str:
    """PowerShell 7+ понимает UTF-8 без BOM; иначе Windows PowerShell 5.1."""
    global _powershell_exe
    if _powershell_exe:
        return _powershell_exe

    pwsh = shutil.which("pwsh")
    _powershell_exe = pwsh if pwsh else "powershell.exe"
    return _powershell_exe


def _com_progid_registered(prog_id: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id):
            return True
    except OSError:
        return False


def _read_1cestart_installed_location() -> str:
    cfg = Path.home() / "AppData" / "Roaming" / "1C" / "1CEStart" / "1cestart.cfg"
    if not cfg.is_file():
        return ""
    for encoding in ("utf-16", "utf-16-le", "utf-8-sig", "utf-8", "cp1251"):
        try:
            text = cfg.read_text(encoding=encoding, errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("InstalledLocation="):
                return stripped.split("=", 1)[1].strip()
    return ""


def _find_platform_bins(installed_location: str) -> list[dict[str, str]]:
    if not installed_location:
        return []

    root = Path(installed_location)
    if not root.is_dir():
        return []

    bins: list[dict[str, str]] = []
    try:
        for version_dir in sorted(root.iterdir(), reverse=True):
            if not version_dir.is_dir():
                continue
            name = version_dir.name
            if not all(part.isdigit() for part in name.split(".") if part):
                continue
            bin_dir = version_dir / "bin"
            dll = bin_dir / "comcntr.dll"
            if not dll.is_file():
                continue
            major = ".".join(name.split(".")[:2]) if "." in name else name
            prog_id = "V85.COMConnector" if major == "8.5" else "V83.COMConnector"
            bins.append(
                {
                    "version": name,
                    "progId": prog_id,
                    "binPath": str(bin_dir),
                    "comcntrDll": str(dll),
                }
            )
    except OSError:
        return bins
    return bins


def _com_status_payload() -> dict[str, Any]:
    v83 = _com_progid_registered("V83.COMConnector")
    v85 = _com_progid_registered("V85.COMConnector")
    installed = _read_1cestart_installed_location()
    ps_exe = _resolve_powershell_exe()
    register_script = str(ROOT / "Register-1CCom.cmd")
    platform_bins = _find_platform_bins(installed)
    actions: list[str] = []

    if not v83 and not v85:
        actions.append(
            f"COM не зарегистрирован. Запустите: {register_script} "
            "(подтвердите UAC). Открывать 1С:Предприятие не нужно."
        )
    elif not v85:
        actions.append(
            "V85.COMConnector не зарегистрирован — базы на платформе 8.5 не подключатся. "
            f"Запустите: {register_script}"
        )
    if not installed:
        actions.append(
            "Не найден InstalledLocation в 1cestart.cfg. Запустите 1С один раз "
            f"или: {register_script} -PlatformPath \"...\\8.5.x.x\\bin\""
        )
    elif not platform_bins:
        actions.append(
            f"Платформа не найдена в {installed}. Проверьте установку 1С или укажите -PlatformPath."
        )

    ready = bool(v83 or v85) and bool(installed) and bool(platform_bins)
    user_message = ""
    if not ready:
        user_message = (
            "COM-коннектор 1С не готов к подключению. "
            f"Запустите файл Register-1CCom.cmd из каталога 1c-analyst-tools "
            f"(полный путь: {register_script}). "
            "Подтвердите запрос UAC — отдельный PowerShell «от администратора» не нужен. "
            "Открывать 1С:Предприятие заранее не требуется. "
            "После регистрации: Settings → MCP → onec-data → Restart, затем повторите connect."
        )

    return {
        "status": "ok" if ready else "error",
        "com": {
            "V83.COMConnector": v83,
            "V85.COMConnector": v85,
        },
        "installedLocation": installed,
        "platformBins": platform_bins,
        "registerScriptPath": register_script,
        "powershell": ps_exe,
        "readyForConnect": ready,
        "actions": actions,
        "userMessage": user_message,
        "hint": (
            "readyForConnect=true — COM и платформа в порядке; Register-1CCom не нужен. "
            "При ошибке connect смотрите errorKind: external_denied = нет права COM у пользователя 1С."
        ),
    }


def _ensure_ps1_utf8_bom() -> None:
    """При старте MCP: если Get-1CData.ps1 без BOM — запустить Fix-AllPs1Utf8Bom.ps1."""
    script = GET_DATA_SCRIPT
    if not script.is_file():
        return
    try:
        head = script.read_bytes()[:3]
    except OSError:
        return
    if head == b"\xef\xbb\xbf":
        return

    fix_script = ROOT / "scripts" / "Fix-AllPs1Utf8Bom.ps1"
    if not fix_script.is_file():
        return

    try:
        subprocess.run(
            [
                _resolve_powershell_exe(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(fix_script),
            ],
            cwd=str(ROOT),
            capture_output=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _startup_self_heal() -> None:
    repair_session_file(ROOT)
    _ensure_ps1_utf8_bom()


_startup_self_heal()

mcp = FastMCP("onec-data")

_memory_session: dict[str, str] | None = None
_verified_target_key: str | None = None
_its_memory: dict[str, str] = {}


def _get_connection() -> dict[str, str]:
    global _memory_session

    connection = resolve_connection(ROOT, _memory_session)
    if not connection:
        raise RuntimeError(
            "AGENT_ACTION (режим live): вызови onec_list_infobases, спроси базу и учётные данные, "
            "затем onec_connect. Если доступа к базе нет — режим offline/research: кейсы, ИТС, форумы; "
            "onec_query не вызывать. Не предлагай скрипты."
        )
    return connection


def _connection_args() -> list[str]:
    return build_connection_args(_get_connection())


def _execute_powershell(args: list[str], timeout: int = 300) -> tuple[str, str, int]:
    cmd = [
        _resolve_powershell_exe(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(GET_DATA_SCRIPT),
        *args,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        com_hint = ""
        com_status = _com_status_payload()
        if not com_status.get("readyForConnect"):
            com_hint = (
                " Возможная причина: COM не готов — вызовите onec_com_status и выполните Register-1CCom.cmd."
            )
        raise RuntimeError(
            f"Таймаут PowerShell ({timeout} с).{com_hint} "
            "onec_connect без platform_version и без refresh_metadata=true; "
            "при успешном connect вызовите onec_refresh_metadata отдельно "
            "(может занять несколько минут). Первый COM-connect иногда 30–60 с. "
            f"Команда: {' '.join(str(part) for part in args[:6])}..."
        ) from exc

    return (
        (result.stdout or "").strip(),
        (result.stderr or "").strip(),
        int(result.returncode),
    )


def _run_powershell(args: list[str], timeout: int = 300) -> str:
    stdout, stderr, returncode = _execute_powershell(args, timeout=timeout)
    if returncode != 0:
        detail = stderr or stdout or f"exit code {returncode}"
        if "ParserError" in detail or "Unexpected token" in detail:
            detail = (
                f"{detail}\n\n"
                "Ошибка парсинга PowerShell: файлы .ps1 должны быть в UTF-8 с BOM "
                "(Windows PowerShell 5.1). Запустите: scripts\\Fix-AllPs1Utf8Bom.ps1"
            )
        raise RuntimeError(detail)
    return stdout


def _parse_powershell_json(output: str, stderr: str = "") -> dict[str, Any]:
    text = (output or "").strip()
    if not text:
        hint = (stderr or "").strip()
        raise RuntimeError(
            "Пустой stdout от Get-1CData.ps1 (ожидался JSON). "
            "Частые причины: COM не зарегистрирован (Register-1CCom.cmd), таймаут, "
            "служебный текст в stdout. "
            f"{hint[:500]}"
        )

    decoder = json.JSONDecoder()
    attempts: list[str] = [text]
    start = text.find("{")
    if start > 0:
        attempts.append(text[start:])

    for candidate in attempts:
        try:
            payload, _end = decoder.raw_decode(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

    for line in reversed(text.splitlines()):
        line_candidate = line.strip()
        if not line_candidate.startswith("{"):
            continue
        try:
            payload = json.loads(line_candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue

    raise RuntimeError(
        "Ответ PowerShell не JSON. Первые 400 символов stdout: "
        f"{text[:400]}"
    )


def _run_powershell_json(args: list[str], timeout: int = 300) -> dict[str, Any]:
    cmd_preview = " ".join(str(part) for part in args[:8])
    try:
        stdout, stderr, returncode = _execute_powershell(args, timeout=timeout)
    except RuntimeError as error:
        message = str(error)
        if "ParserError" in message or "Unexpected token" in message:
            raise
        raise RuntimeError(f"{message}\nКоманда: {cmd_preview}") from error

    try:
        payload = _parse_powershell_json(stdout, stderr)
    except RuntimeError as error:
        if returncode != 0:
            detail = stderr or stdout or f"exit code {returncode}"
            raise RuntimeError(f"{detail}\nКоманда: {cmd_preview}") from error
        raise RuntimeError(f"{error}\nКоманда: {cmd_preview}") from error

    if returncode != 0 and str(payload.get("status", "")).lower() != "error":
        detail = stderr or stdout or f"exit code {returncode}"
        raise RuntimeError(f"{detail}\nКоманда: {cmd_preview}")

    return payload


def _is_verified(connection: dict[str, str]) -> bool:
    global _verified_target_key

    if not _verified_target_key:
        return False

    return _verified_target_key == connection_target_key(connection)


def _mark_verified(connection: dict[str, str]) -> None:
    global _verified_target_key

    _verified_target_key = connection_target_key(connection)


def _clear_verified() -> None:
    global _verified_target_key

    _verified_target_key = None


def _store_session(session: dict[str, str]) -> dict[str, str]:
    global _memory_session

    _memory_session = session
    _clear_verified()
    save_session(ROOT, session)
    return public_view(session)


def _metadata_cache_relative() -> str | None:
    connection = resolve_connection(ROOT, _memory_session)
    if not connection:
        return None

    cache_path = connection.get("metadata_cache", "").strip()
    return cache_path or None


def _current_session() -> dict[str, str] | None:
    return resolve_connection(ROOT, _memory_session)


def _obsidian_database_from_session(session: dict[str, str] | None) -> str:
    if not session:
        return resolve_database_name(None, analyst_root=ROOT)
    return resolve_database_name(session, analyst_root=ROOT)


def _persist_obsidian_context(
    database_name: str = "",
    project_name: str = "",
    extension_name: str = "",
) -> dict[str, str] | None:
    global _memory_session

    connection = resolve_connection(ROOT, _memory_session)
    if not connection:
        return None

    updated = dict(connection)
    db = (database_name or project_name).strip()
    if db:
        updated["obsidian_database"] = db
    if extension_name.strip():
        updated["obsidian_extension"] = extension_name.strip()

    _memory_session = updated
    save_session(ROOT, updated)
    return updated


def _apply_infobase_labels(session: dict[str, str], *, display_name: str = "") -> dict[str, str]:
    """Дополняет сессию именем ИБ для папки .Obsidian/{база}/."""
    updated = dict(session)
    label = display_name.strip()
    if not label:
        ib_path = updated.get("info_base_path", "").strip()
        if ib_path:
            label = Path(ib_path).name
        elif updated.get("server") and updated.get("ref"):
            label = f"{updated['server']}_{updated['ref']}"

    if label:
        updated["info_base_display_name"] = label
        if not updated.get("obsidian_database", "").strip():
            updated["obsidian_database"] = resolve_database_name(updated, analyst_root=ROOT)

    return updated


def _publish_metadata_library(session: dict[str, str]) -> None:
    cache_relative = session.get("metadata_cache", "").strip()
    cache_dir = resolve_cache_dir(ROOT, cache_relative)
    if not cache_dir:
        return

    manifest = load_manifest(cache_dir)
    if not manifest:
        return

    library_path = publish_metadata_to_library(ROOT, cache_dir, manifest)
    manifest["libraryPath"] = library_path


def _refresh_metadata(force: bool = False) -> dict:
    args = _connection_args()
    args.append("-ExportMetadata")
    args.append("-AgentMode")
    if force:
        args.append("-ForceMetadataRefresh")

    manifest = _run_powershell_json(args, timeout=900)
    if not manifest.get("ready"):
        raise RuntimeError("Выгрузка метаданных не завершилась успешно.")

    global _memory_session
    connection = _get_connection()
    updated = update_session_metadata_cache(connection, manifest)
    _memory_session = updated
    save_session(ROOT, updated)
    _publish_metadata_library(updated)
    return manifest


@mcp.tool()
def onec_ping() -> str:
    """Проверка доступности MCP onec-data (быстрый ответ без COM)."""
    return json.dumps(
        {
            "status": "ok",
            "server": "onec-data",
            "root": str(ROOT),
            "powershell": _resolve_powershell_exe(),
            "hint": "Если ping ok, а connect пропал — onec_com_status, затем Restart MCP.",
        },
        ensure_ascii=False,
    )


@mcp.tool()
def onec_com_status() -> str:
    """Статус COM-коннекторов 1С (V83/V85) и 1cestart.cfg — без подключения к базе."""
    return json.dumps(_com_status_payload(), ensure_ascii=False)


def _reset_session_on_welcome(first_user_message: str) -> dict[str, Any]:
    global _memory_session

    def _clear_memory() -> None:
        global _memory_session
        _memory_session = None

    return reset_session_for_new_chat(
        ROOT,
        _memory_session,
        first_user_message,
        clear_memory=_clear_memory,
        clear_verified=_clear_verified,
        clear_session_file=clear_session,
    )


@mcp.tool()
def onec_welcome(first_user_message: str = "") -> str:
    """Приветствие для новой сессии: меню задач для question + технический контекст для агента.

    first_user_message — текст первого сообщения пользователя.
    Пользователю показывать formatted_user; варианты выбора — через question (поле question).
    formatted (MCP-список) — только для агента, не в чат.
    """
    session_reset = _reset_session_on_welcome(first_user_message)
    return welcome_payload_json(ROOT, _memory_session, session_reset=session_reset)


@mcp.tool()
def onec_list_infobases() -> str:
    """Возвращает список информационных баз из реестра ibases.v8i пользователя Windows."""
    output = _run_powershell(["-ListInfoBases", "-OutputFormat", "Json"])
    return output


@mcp.tool()
def onec_connection_status() -> str:
    """Возвращает текущие настройки подключения к базе (без пароля)."""
    connection = resolve_connection(ROOT, _memory_session)
    if not connection:
        return json.dumps(
            {
                "connected": False,
                "session_saved": False,
                "message": (
                    "AGENT_ACTION (режим live): onec_list_infobases → спросить базу/логин/пароль → onec_connect. "
                    "Если доступа к ИБ нет — offline/research без connect. Не предлагать скрипты."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    payload = public_view(connection)
    payload["session_saved"] = True
    payload["connected"] = _is_verified(connection)
    session = connection
    payload["metadata"] = metadata_status(ROOT, _metadata_cache_relative(), session)

    if payload["connected"]:
        payload["message"] = "Подключение подтверждено в текущей сессии MCP."
    else:
        payload["message"] = (
            "AGENT_ACTION (режим live): сохранённая сессия не активна — спроси базу/логин/пароль и onec_connect. "
            "Если доступа к ИБ нет — работай в offline/research без onec_query."
        )

    cases_payload: dict[str, Any] = {
        "count": 0,
        "matches": [],
        "mustReviewBeforeInvestigation": False,
    }
    case_query = " ".join(
        part
        for part in [
            str(payload.get("target", "")),
            str(payload["metadata"].get("configurationName", "")),
        ]
        if part
    ).strip()
    if case_query:
        try:
            cases_payload = search_cases(
                ROOT,
                case_query,
                configuration_name=str(payload["metadata"].get("configurationName", "")),
                limit=3,
            )
        except ValueError:
            pass
    payload["cases"] = cases_payload

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _list_infobases_payload() -> list[dict]:
    output = _run_powershell(["-ListInfoBases", "-OutputFormat", "Json"])
    payload = json.loads(output)
    if not isinstance(payload, list):
        raise RuntimeError("Неожиданный формат списка баз.")
    return payload


@mcp.tool()
def onec_connect(
    user: str,
    info_base_path: str = "",
    info_base_name: str = "",
    server: str = "",
    ref: str = "",
    password: str = "",
    platform_version: str = "",
    connection_string: str = "",
    refresh_metadata: bool = False,
) -> str:
    """Подключение к ИБ 1С (read-only). Обязателен user.

    Предпочтительно: info_base_name — имя или номер (1, 2, …) из onec_list_infobases.
    Альтернатива: info_base_path — только каталог (без префикса File=).

    По умолчанию только проверка COM (быстро). refresh_metadata=true — полная выгрузка
    метаданных в том же вызове (долго, риск таймаута клиента). Иначе после connect:
    onec_refresh_metadata.

    platform_version не передавайте — подбор по версии ИБ и 1cestart.cfg.
    """
    global _memory_session

    ignored_platform_version = platform_version.strip()
    platform_version = ""

    merged = merge_connect_inputs(
        info_base_path=info_base_path,
        info_base_name=info_base_name,
        server=server,
        ref=ref,
        user=user,
        password=password,
        connection_string=connection_string,
    )
    user = merged["user"]
    info_base_path = merged["info_base_path"]
    info_base_name = merged["info_base_name"]
    server = merged["server"]
    ref = merged["ref"]
    password = merged["password"]

    if not user:
        raise ValueError(
            "Параметр user обязателен (имя пользователя 1С). "
            "Пример вызова: user=\"Администратор\", info_base_name=\"1\" "
            "или info_base_path=\"C:\\\\Users\\\\...\\\\DemoTrd\"."
        )

    previous = resolve_connection(ROOT, _memory_session)
    ib_display_name = info_base_name.strip()

    if info_base_name and not info_base_path and not (server and ref):
        bases = _list_infobases_payload()
        resolved = resolve_base_from_list(bases, info_base_name)
        info_base_path = resolved.get("info_base_path", "").strip()
        server = resolved.get("server", "").strip()
        ref = resolved.get("ref", "").strip()
        ib_display_name = str(resolved.get("display_name") or ib_display_name).strip()

    if info_base_path:
        info_base_path = normalize_info_base_path(info_base_path)

    if info_base_path:
        session = {
            "info_base_path": info_base_path,
            "server": "",
            "ref": "",
            "user": user,
            "password": password,
            "platform_version": "",
            "metadata_cache": "",
        }
    elif server and ref:
        session = {
            "info_base_path": "",
            "server": server,
            "ref": ref,
            "user": user,
            "password": password,
            "platform_version": "",
            "metadata_cache": "",
        }
    else:
        raise ValueError(
            "Укажите цель подключения: info_base_name (имя или номер из onec_list_infobases), "
            "info_base_path (каталог файловой базы без File=) или server + ref. "
            "Строку File=\"...\" из реестра можно передать в connection_string, не в info_base_path."
        )

    session = _apply_infobase_labels(session, display_name=ib_display_name)
    target_changed = bool(previous and not targets_equal(previous, session))

    _store_session(session)

    args = build_connection_args(session, include_prefer_version=False)
    args.extend([
        "-AgentMode",
        "-Query",
        "ВЫБРАТЬ 1 КАК Connected",
        "-MaxRows",
        "1",
    ])
    output_payload = _run_powershell_json(args, timeout=420)
    if str(output_payload.get("status", "")).lower() == "error":
        message = str(output_payload.get("message", "Ошибка подключения к базе."))
        error_kind = str(output_payload.get("errorKind") or classify_connect_error(message))
        hint = agent_hint_for_error(error_kind, str(ROOT / "Register-1CCom.cmd"))
        raise RuntimeError(f"{message}\n\n{hint}")

    payload = output_payload
    payload["status"] = "ok"
    payload["connection"] = public_view(session)
    payload["target_changed"] = target_changed

    platform_block = payload.get("platform")
    if isinstance(platform_block, dict):
        payload["platform_note"] = (
            f"Платформа подобрана автоматически: {platform_block.get('version', '')} "
            f"({platform_block.get('progId', '')}). Параметр platform_version агенту не передавать."
        )
        session["platform_version"] = str(platform_block.get("major") or "").strip()
        _memory_session = session
        save_session(ROOT, session)

    if ignored_platform_version:
        payload["ignored_platform_version"] = ignored_platform_version
        payload["platform_version_note"] = (
            "Параметр platform_version игнорируется — платформа подбирается автоматически."
        )

    if target_changed:
        payload["notice"] = (
            "База изменена. Используй только те логин и пароль, которые пользователь указал "
            "для этой базы."
        )

    _mark_verified(session)

    metadata_manifest: dict[str, Any] | None = None
    reused_cache = False

    if refresh_metadata:
        if not target_changed:
            cached = find_metadata_cache_for_target(
                ROOT,
                info_base_path=session.get("info_base_path", ""),
                server=session.get("server", ""),
                ref=session.get("ref", ""),
            )
            if cached:
                _memory_session = update_session_metadata_cache(session, cached)
                save_session(ROOT, _memory_session)
                metadata_manifest = cached
                reused_cache = True

        if not reused_cache:
            metadata_manifest = _refresh_metadata(force=target_changed)
    else:
        cached = find_metadata_cache_for_target(
            ROOT,
            info_base_path=session.get("info_base_path", ""),
            server=session.get("server", ""),
            ref=session.get("ref", ""),
        )
        if cached:
            _memory_session = update_session_metadata_cache(session, cached)
            save_session(ROOT, _memory_session)
            metadata_manifest = cached
            reused_cache = True
        payload["metadata_next_step"] = (
            "AGENT_ACTION: connect успешен. Вызовите onec_refresh_metadata для кэша метаданных "
            "(отдельный долгий вызов; не объединяйте с connect)."
        )

    session = resolve_connection(ROOT, _memory_session) or session
    payload["metadata"] = metadata_status(ROOT, _metadata_cache_relative(), session)
    if metadata_manifest is not None:
        payload["metadata_export"] = metadata_manifest
    if reused_cache:
        payload["metadata_note"] = "Использован существующий кэш метаданных."
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_refresh_metadata(force: bool = False) -> str:
    """Принудительно обновляет кэш метаданных конфигурации из подключённой ИБ."""
    manifest = _refresh_metadata(force=force)
    return json.dumps(manifest, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_metadata_status() -> str:
    """Возвращает статус кэша метаданных текущей конфигурации."""
    session = _current_session()
    payload = metadata_status(ROOT, _metadata_cache_relative(), session)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_metadata_search(query: str, limit: int = 20) -> str:
    """Ищет объекты метаданных по имени, синониму или типу в кэше конфигурации."""
    session = _current_session() or {}
    payload = metadata_search(ROOT, _metadata_cache_relative(), query, limit, session)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_metadata_object(full_name: str) -> str:
    """Возвращает карточку объекта метаданных: реквизиты, ТЧ, измерения регистра."""
    session = _current_session() or {}
    payload = metadata_object(ROOT, _metadata_cache_relative(), full_name, session)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_search_cases(query: str, limit: int = 5) -> str:
    """Ищет похожие кейсы расследований. Вызывать перед расследованием."""
    session = _current_session() or {}
    payload = search_cases(
        ROOT,
        query,
        configuration_name=str(session.get("configuration_name", "")),
        database_name=_obsidian_database_from_session(session),
        limit=limit,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_get_case(case_id: str) -> str:
    """Возвращает полный кейс расследования по id."""
    payload = get_case(ROOT, case_id)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_investigation_status() -> str:
    """Активное расследование в сессии: case_id и путь заметки Sessions для дополнения."""
    payload = tracker_status(ROOT)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_save_case(
    symptom: str = "",
    correct_solution: str = "",
    wrong_approach: str = "",
    tags: str = "",
    queries_used: str = "",
    objects_used: str = "",
    case_id: str = "",
    status: str = "",
    context_summary: str = "",
    investigation_path: str = "",
    methods_applied: str = "",
    hypotheses: str = "",
    sources_used: str = "",
    checklist: str = "",
    additional_notes: str = "",
) -> str:
    """Сохраняет или дополняет кейс расследования (JSON + Obsidian Cases/).

    При приближении к решению — status=draft с полным контекстом.
    При доп. вопросах пользователя — тот же case_id + additional_notes.
    status=final — когда решение подтверждено (нужен correct_solution).
    """
    session = _current_session() or {}
    tracker = load_tracker(ROOT) or {}
    case_id = case_id.strip() or str(tracker.get("caseId", "")).strip()

    tag_list = [part.strip() for part in tags.split(",") if part.strip()]
    query_list = [part.strip() for part in queries_used.split(";") if part.strip()]
    object_list = [part.strip() for part in objects_used.split(";") if part.strip()]
    methods_list = [part.strip() for part in methods_applied.split(";") if part.strip()]
    sources_list = [part.strip() for part in sources_used.split(";") if part.strip()]

    payload = save_case(
        ROOT,
        symptom=symptom,
        correct_solution=correct_solution,
        wrong_approach=wrong_approach,
        configuration_name=str(session.get("configuration_name", "")),
        configuration_version=str(session.get("configuration_version", "")),
        tags=tag_list,
        queries_used=query_list,
        objects_used=object_list,
        verified_by_analyst=True,
        case_id=case_id,
        status=status,
        context_summary=context_summary,
        investigation_path=investigation_path,
        methods_applied=methods_list,
        hypotheses=hypotheses,
        sources_used=sources_list,
        checklist=checklist,
        additional_notes=additional_notes,
    )

    case_rel = str(tracker.get("caseRelativePath", ""))
    try:
        obsidian_result = save_case_note(
            ROOT,
            payload,
            database_name=_obsidian_database_from_session(session),
            configuration_name=str(session.get("configuration_name", "")),
            extension_name=str(session.get("obsidian_extension", "")),
            session=session,
            existing_relative_path=case_rel,
        )
        payload["obsidian"] = obsidian_result
        register_investigation(
            ROOT,
            case_id=str(payload.get("id", "")),
            case_relative_path=obsidian_result.get("relative_path", ""),
            session_relative_path=str(tracker.get("sessionRelativePath", "")),
            status=str(payload.get("status", status)),
            symptom=str(payload.get("symptom", symptom)),
        )
        if str(payload.get("status", "")).lower() == "final":
            update_tracker_paths(ROOT, status="final")
    except OSError as error:
        payload["obsidian"] = {"saved": False, "error": str(error)}

    payload["agent_action"] = (
        "AGENT_ACTION: при доп. вопросах — onec_save_case(case_id=..., additional_notes=...) "
        "и onec_obsidian_append_session. Ищите позже через onec_search_cases в Obsidian."
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_disconnect() -> str:
    """Сбрасывает сохранённое подключение к базе 1С."""
    global _memory_session

    _memory_session = None
    _clear_verified()
    clear_session(ROOT)
    return json.dumps({"connected": False, "session_saved": False}, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_check_connection() -> str:
    """Проверяет подключение к текущей базе простым read-only запросом."""
    args = _connection_args()
    args.extend([
        "-AgentMode",
        "-Query",
        "ВЫБРАТЬ 1 КАК Connected",
        "-MaxRows",
        "1",
    ])
    payload = _run_powershell_json(args)
    if str(payload.get("status", "")).lower() == "error":
        raise RuntimeError(str(payload.get("message", "Ошибка проверки подключения.")))
    payload["status"] = "ok"
    payload["connection"] = public_view(_get_connection())
    payload["metadata"] = metadata_status(ROOT, _metadata_cache_relative(), _get_connection())
    _mark_verified(_get_connection())
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_read_module(
    full_name: str,
    module_part: str = "manager",
    max_lines: int = 400,
    force_refresh: bool = False,
) -> str:
    """Читает текст модуля конфигурации из подключённой ИБ через конфигуратор (частичная выгрузка).

    full_name — полное имя объекта, например Документ.ЗаказКлиента или ОбщийМодуль.ПроведениеДокументов.
    module_part: manager (модуль менеджера), object (модуль объекта), module (общий модуль).
    Требует успешного onec_connect. Может занять 1–3 минуты при первой выгрузке объекта.
    """
    full_name = full_name.strip()
    module_part = module_part.strip().lower()
    if module_part not in {"manager", "object", "module"}:
        raise ValueError("module_part: manager, object или module.")

    if max_lines < 50:
        max_lines = 50
    if max_lines > 2000:
        max_lines = 2000

    connection = _get_connection()
    args = build_connection_args(connection)
    args.extend([
        "-ReadModule",
        "-ModuleFullName",
        full_name,
        "-ModulePart",
        module_part,
        "-ModuleMaxLines",
        str(max_lines),
        "-TargetKey",
        connection_target_key(connection),
        "-AgentMode",
    ])
    if force_refresh:
        args.append("-ForceModuleRefresh")

    payload = _run_powershell_json(args, timeout=600)
    payload["note"] = (
        "COM не читает BSL напрямую — модуль выгружается конфигуратором. "
        "Предпочтительно: onec_config_sources_register (готовые XML) "
        "или onec_config_read_module из зарегистрированных исходников."
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_config_sources_status() -> str:
    """Статус зарегистрированных каталогов XML-исходников конфигурации для анализа BSL."""
    payload = sources_status(ROOT)
    session = _current_session()
    if session:
        payload["session_target_key"] = connection_target_key(session)
        payload["configuration_name"] = str(session.get("configuration_name", ""))
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_config_sources_register(
    sources_path: str,
    label: str = "",
    configuration_name: str = "",
    set_active: bool = True,
) -> str:
    """Регистрирует существующий каталог выгрузки конфигурации (XML/BSL) для анализа кода.

    Сначала спросите пользователя — возможно, исходники уже есть (Git, каталог разработки).
    """
    session = _current_session() or {}
    source = register_source(
        ROOT,
        sources_path,
        label=label,
        configuration_name=configuration_name or str(session.get("configuration_name", "")),
        target_key=connection_target_key(session) if session else "",
        origin="register",
        set_active=set_active,
    )
    return json.dumps(
        {
            "status": "ok",
            "message": "Источник XML зарегистрирован. Для чтения кода: onec_config_read_module / onec_config_search_code.",
            "source": source,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def onec_config_sources_unregister(source_id: str = "") -> str:
    """Снимает регистрацию каталога исходников (пустой source_id — очистить все)."""
    payload = unregister_source(ROOT, source_id)
    payload["status"] = "ok"
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_dump_config(
    mode: str = "partial",
    objects: str = "",
    output_path: str = "",
    extension: str = "",
) -> str:
    """Выгружает конфигурацию из подключённой ИБ в XML-файлы через конфигуратор (DumpConfigToFiles).

    mode: partial (список objects обязателен) или full (вся конфигурация, долго).
    Требует onec_connect. После выгрузки каталог регистрируется автоматически.
    """
    mode_normalized = mode.strip().lower()
    if mode_normalized not in {"partial", "full"}:
        raise ValueError("mode: partial или full.")

    object_list = [part.strip() for part in objects.replace(";", ",").split(",") if part.strip()]
    if mode_normalized == "partial" and not object_list:
        raise ValueError(
            "Для partial укажите objects, например: "
            "Документ.ЗаказКлиента,ОбщийМодуль.ПроведениеДокументов"
        )

    connection = _get_connection()
    args = build_connection_args(connection)
    args.extend([
        "-DumpConfig",
        "-DumpMode",
        mode_normalized.capitalize(),
        "-DumpTargetKey",
        connection_target_key(connection),
        "-AgentMode",
    ])
    if object_list:
        args.extend(["-DumpObjects", ",".join(object_list)])
    if output_path.strip():
        args.extend(["-DumpOutputPath", output_path.strip()])
    if extension.strip():
        args.extend(["-DumpExtension", extension.strip()])

    timeout = 1800 if mode_normalized == "full" else 900
    payload = _run_powershell_json(args, timeout=timeout)
    out_dir = str(payload.get("outDir", "")).strip()
    if out_dir:
        source = register_source(
            ROOT,
            out_dir,
            label=connection.get("info_base_display_name", "") or Path(out_dir).name,
            configuration_name=str(connection.get("configuration_name", "")),
            target_key=connection_target_key(connection),
            origin="dump",
            set_active=True,
        )
        payload["registered_source"] = source
        payload["next_step"] = (
            "AGENT_ACTION: onec_config_read_module / onec_config_search_code — анализ BSL; "
            "для ЛТ обновите §4 фактами из кода."
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_config_read_module(
    full_name: str,
    module_part: str = "manager",
    max_lines: int = 400,
    source_id: str = "",
) -> str:
    """Читает модуль BSL из зарегистрированного каталога XML-исходников (без COM/конфигуратора)."""
    payload = read_module_from_sources(
        ROOT,
        full_name,
        module_part=module_part,
        source_id=source_id,
        max_lines=max_lines,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_config_search_code(
    query: str,
    limit: int = 15,
    source_id: str = "",
) -> str:
    """Поиск по BSL-модулям в зарегистрированных XML-исходниках конфигурации."""
    payload = search_code_in_sources(ROOT, query, source_id=source_id, limit=limit)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_query(query: str, max_rows: int = 500) -> str:
    """Выполняет read-only запрос на языке запросов 1С и возвращает JSON с данными."""
    if not query or not query.strip():
        raise ValueError("Параметр query не может быть пустым.")

    normalized = " ".join(query.split())
    if not normalized.upper().startswith(("ВЫБРАТЬ", "SELECT")):
        raise ValueError("Разрешены только запросы ВЫБРАТЬ/SELECT.")

    if max_rows < 1:
        max_rows = 1
    if max_rows > 5000:
        max_rows = 5000

    args = _connection_args()
    args.extend([
        "-AgentMode",
        "-Query",
        query,
        "-MaxRows",
        str(max_rows),
    ])
    payload = _run_powershell_json(args)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_web_research_status() -> str:
    """Проверяет настройку веб-поиска. Если ИТС не настроен — вернёт AGENT_ACTION: спросить логин/пароль у пользователя."""
    payload = web_research_status(ROOT, _its_memory)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_its_configure(user: str, password: str) -> str:
    """Сохраняет логин и пароль портала 1С:ИТС для текущей сессии MCP и проверяет авторизацию."""
    payload = configure_its_payload(ROOT, user, password, _its_memory)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_its_disconnect() -> str:
    """Сбрасывает сохранённые учётные данные ИТС (память и .onec-web.json)."""
    payload = clear_its_payload(ROOT, _its_memory)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_web_search_forums(
    query: str,
    configuration_name: str = "",
    configuration_version: str = "",
    limit: int = 5,
) -> str:
    """Ищет по форумам 1С (Infostart, Mista и др.). Результаты могут быть неактуальны для вашей версии конфигурации."""
    payload = search_forums_payload(
        ROOT,
        query,
        configuration_name=configuration_name,
        configuration_version=configuration_version,
        limit=limit,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_its_search(query: str, database: str = "v8std", limit: int = 5) -> str:
    """Поиск в документации 1С:ИТС. Без учётных данных вернёт AGENT_ACTION — спроси логин/пароль и onec_its_configure."""
    payload = search_its_payload(ROOT, query, database=database, limit=limit, its_memory=_its_memory)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_its_fetch(url: str, max_chars: int = 12000) -> str:
    """Загружает текст статьи с its.1c.ru. Без учётных данных вернёт AGENT_ACTION."""
    if max_chars < 1000:
        max_chars = 1000
    if max_chars > 50000:
        max_chars = 50000

    payload = fetch_its_payload(ROOT, url, max_chars=max_chars, its_memory=_its_memory)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_obsidian_status() -> str:
    """Статус vault .Obsidian: путь, папки ИБ, число кейсов. Папка базы — из onec_connect или database_name."""
    session = _current_session()
    payload = vault_status(ROOT, session)
    if session:
        payload["session_context"] = resolve_context(session=session, analyst_root=ROOT)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_obsidian_set_context(
    database_name: str = "",
    project_name: str = "",
    extension_name: str = "",
) -> str:
    """Задаёт имя папки ИБ в .Obsidian (сохраняется в сессии). database_name — приоритет; project_name — устаревший алиас."""
    db_override = (database_name or project_name).strip()
    updated = _persist_obsidian_context(database_name, project_name, extension_name)

    if not updated and not db_override:
        context = resolve_context(extension_name=extension_name, analyst_root=ROOT)
        return json.dumps(
            {
                "saved": False,
                "message": (
                    "Нет connect — передайте database_name в save_* или задайте ONEC_OBSIDIAN_DATABASE."
                ),
                "context": context,
                "vault": vault_status(ROOT, None),
            },
            ensure_ascii=False,
            indent=2,
        )

    session_for_context = updated or _current_session() or {}
    context = resolve_context(
        database_name=db_override,
        extension_name=extension_name,
        session=session_for_context,
        analyst_root=ROOT,
    )
    return json.dumps(
        {
            "saved": bool(updated),
            "context": context,
            "vault": vault_status(ROOT, session_for_context),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def onec_obsidian_save_requirements(
    body_markdown: str,
    title: str = "Лист требований",
    database_name: str = "",
    project_name: str = "",
    configuration_name: str = "",
    extension_name: str = "",
    phase: str = "draft",
    slug: str = "",
) -> str:
    """Сохраняет лист требований в .Obsidian/{база}/Requirements/YYYY-MM-DD-slug.md"""
    session = _current_session() or {}
    payload = save_requirements_note(
        ROOT,
        title=title,
        body_markdown=body_markdown,
        database_name=database_name or project_name or _obsidian_database_from_session(session),
        configuration_name=configuration_name or str(session.get("configuration_name", "")),
        extension_name=extension_name or str(session.get("obsidian_extension", "")),
        session=session,
        phase=phase,
        slug=slug,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_obsidian_save_session(
    summary: str,
    transcript_markdown: str = "",
    database_name: str = "",
    project_name: str = "",
    configuration_name: str = "",
    extension_name: str = "",
    mode: str = "",
    slug: str = "",
) -> str:
    """Сохраняет историю сессии в .Obsidian/{база}/Sessions/YYYY-MM-DD_HHMM-slug.md"""
    session = _current_session() or {}
    payload = save_session_note(
        ROOT,
        summary=summary,
        transcript_markdown=transcript_markdown,
        database_name=database_name or project_name or _obsidian_database_from_session(session),
        configuration_name=configuration_name or str(session.get("configuration_name", "")),
        extension_name=extension_name or str(session.get("obsidian_extension", "")),
        session=session,
        mode=mode,
        slug=slug,
    )
    tracker = load_tracker(ROOT)
    if tracker and tracker.get("caseId"):
        register_investigation(
            ROOT,
            case_id=str(tracker.get("caseId", "")),
            case_relative_path=str(tracker.get("caseRelativePath", "")),
            session_relative_path=str(payload.get("relative_path", "")),
            status=str(tracker.get("status", "draft")),
            symptom=str(tracker.get("symptom", "")),
        )
    else:
        register_investigation(
            ROOT,
            case_id="",
            session_relative_path=str(payload.get("relative_path", "")),
            status="draft",
            symptom=summary[:240],
        )
    payload["agent_action"] = (
        "AGENT_ACTION: дополняйте эту заметку через onec_obsidian_append_session "
        f"(session_note_path={payload.get('relative_path', '')})."
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_obsidian_append_session(
    content: str,
    section: str = "Дополнение",
    session_note_path: str = "",
) -> str:
    """Дополняет заметку Sessions новым разделом (доп. вопросы, уточнения, новые гипотезы)."""
    tracker = load_tracker(ROOT) or {}
    rel_path = session_note_path.strip() or str(tracker.get("sessionRelativePath", "")).strip()
    payload = append_session_note(
        ROOT,
        section=section,
        content=content,
        session_note_path=rel_path,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_obsidian_prepare_requirements(
    task_description: str,
    configuration_name: str = "",
    database_name: str = "",
) -> str:
    """Перед ЛТ: похожие кейсы/ЛТ в Obsidian, справочники конфигурации, шаги поиска в ИТС/интернете."""
    session = _current_session() or {}
    payload = prepare_requirements_context(
        ROOT,
        task_description,
        configuration_name=configuration_name or str(session.get("configuration_name", "")),
        database_name=database_name or _obsidian_database_from_session(session),
        session=session,
    )
    config_name = str(payload.get("configurationName") or "")
    payload["bitmedic"] = bitmedic_search_guidance(
        task_description,
        configuration_name=config_name,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_obsidian_search_handbooks(
    query: str,
    database_name: str = "",
    limit: int = 5,
) -> str:
    """Поиск в .Obsidian/{база}/Справочники — типовой функционал конфигурации."""
    session = _current_session() or {}
    payload = search_handbooks(
        ROOT,
        query,
        database_name=database_name or _obsidian_database_from_session(session),
        session=session,
        limit=limit,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def onec_bitmedic_guidance(query: str, configuration_name: str = "") -> str:
    """Подсказка поиска на info.bitmedic.ru для отраслевых конфигураций БИТ.Медицина."""
    session = _current_session() or {}
    config = configuration_name or str(session.get("configuration_name", ""))
    payload = bitmedic_search_guidance(query, configuration_name=config)
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
