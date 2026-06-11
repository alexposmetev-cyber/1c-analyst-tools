"""Шифрование секретов 1С (пароли ИБ и ИТС) через Windows DPAPI.

DPAPI привязывает шифртекст к текущему пользователю Windows: расшифровать
сможет только тот же аккаунт на той же машине. Файлы .onec-session.json /
.onec-web.json перестают содержать пароли открытым текстом.

Fallback: если DPAPI недоступен (не Windows, нет pywin32), значение
хранится как есть, но помечается префиксом — чтобы код всегда знал,
зашифровано оно или нет, и не пытался «расшифровать» обычную строку.
"""

from __future__ import annotations

import base64
import sys

# Префиксы-маркеры в JSON, чтобы различать форматы хранения.
_ENC_PREFIX = "dpapi:"      # зашифровано DPAPI
_PLAIN_PREFIX = "plain:"    # явный plaintext (DPAPI был недоступен)


def _dpapi_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32crypt  # noqa: F401
        return True
    except ImportError:
        return False


def encrypt_secret(value: str) -> str:
    """Шифрует секрет для хранения в файле. Пустую строку возвращает как есть."""
    if not value:
        return ""
    if _dpapi_available():
        try:
            import win32crypt

            blob = win32crypt.CryptProtectData(value.encode("utf-8"), "1c-analyst", None, None, None, 0)
            return _ENC_PREFIX + base64.b64encode(blob).decode("ascii")
        except Exception:  # noqa: BLE001 — деградируем до plaintext, но помечаем
            pass
    return _PLAIN_PREFIX + value


def decrypt_secret(stored: str) -> str:
    """Достаёт исходный секрет из хранимого значения (любой формат)."""
    if not stored:
        return ""
    if stored.startswith(_ENC_PREFIX):
        if not _dpapi_available():
            # Зашифровано на другой машине/аккаунте — расшифровать нельзя.
            return ""
        try:
            import win32crypt

            blob = base64.b64decode(stored[len(_ENC_PREFIX):])
            _desc, data = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
            return data.decode("utf-8")
        except Exception:  # noqa: BLE001
            return ""
    if stored.startswith(_PLAIN_PREFIX):
        return stored[len(_PLAIN_PREFIX):]
    # Обратная совместимость: старые файлы без префикса — это plaintext.
    return stored


def is_encrypted(stored: str) -> bool:
    return bool(stored) and stored.startswith(_ENC_PREFIX)


def storage_mode() -> str:
    """Для диагностики: какой режим хранения сейчас активен."""
    return "dpapi" if _dpapi_available() else "plaintext"
