"""Классификация ошибок подключения COM — однозначные подсказки агенту."""

from __future__ import annotations


def classify_connect_error(message: str) -> str:
    text = (message or "").lower()

    if any(
        marker in text
        for marker in (
            "неверно указано имя пользователя",
            "неверный пароль",
            "неправильный пароль",
            "incorrect password",
            "authentication failed",
            "ошибка аутентификации",
        )
    ):
        return "auth"

    if any(
        marker in text
        for marker in (
            "внешнее соединение",
            "внешнего соединения",
            "не разрешено для указанного пользователя",
            "не разрешено для пользователя 1с:предприятие",
            "external connection",
        )
    ):
        return "external_denied"

    if "parsererror" in text or "unexpected token" in text or "utf-8 bom" in text:
        return "parser"

    if any(
        marker in text
        for marker in (
            "не найдена среди установленных",
            "platform not found",
            "платформа 1с не найдена",
        )
    ):
        return "platform"

    if any(
        marker in text
        for marker in (
            "разрешено только",
            "отверг запрос",
            "connection refused",
            "блокиров",
            "уже начат",
        )
    ):
        return "session_lock"

    if any(
        marker in text
        for marker in (
            "com не зарегистрирован",
            "com-коннектор не зарегистрирован",
            "не зарегистрирован после regsvr32",
            "gettypefromprogid",
        )
    ):
        return "com"

    return "connect"


def agent_hint_for_error(error_kind: str, register_script: str = "") -> str:
    hints = {
        "auth": (
            "AGENT_ACTION: ошибка учётных данных. Спроси у пользователя точное имя пользователя 1С "
            "и пароль для этой базы (как в окне входа). Не упоминай COM, 1cestart.cfg и Register-1CCom."
        ),
        "external_denied": (
            "AGENT_ACTION: COM зарегистрирован (onec-data_onec_com_status ok), но пользователю 1С запрещено "
            "внешнее (COM) подключение. Попроси другого пользователя с правом COM или настройку в "
            "конфигураторе (Administration / права пользователя). Register-1CCom.cmd НЕ нужен."
        ),
        "parser": (
            "AGENT_ACTION: ошибка кодировки .ps1. MCP перезапустится с автоисправлением BOM; "
            "если повторится — scripts\\Fix-AllPs1Utf8Bom.cmd и Restart MCP."
        ),
        "platform": (
            "AGENT_ACTION: повтори onec-data_onec_connect без platform_version. "
            "Не создавай 1cestart.cfg вручную — используется %APPDATA%\\1C\\1CEStart\\1cestart.cfg."
        ),
        "com": (
            f"AGENT_ACTION: onec-data_onec_com_status COM=false — регистрация comcntr.dll только с правами "
            f"администратора Windows. Попроси IT выполнить {register_script or 'Register-1CCom.cmd'} "
            "или regsvr32 на comcntr.dll. Пользователь без админа сам не зарегистрирует. "
            "Предложи offline/research до решения IT. Если COM=true — Register-1CCom не нужен."
        ),
        "session_lock": (
            "AGENT_ACTION: база занята другим сеансом. Попроси закрыть 1С для этой базы. "
            "Register-1CCom.cmd не нужен."
        ),
        "connect": (
            "AGENT_ACTION: уточни у пользователя базу, логин и пароль; onec-data_onec_connect без platform_version. "
            "Если onec-data_onec_com_status readyForConnect=true — Register-1CCom не предлагать."
        ),
    }
    return hints.get(error_kind, hints["connect"])
