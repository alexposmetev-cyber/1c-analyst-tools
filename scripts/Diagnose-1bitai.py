#!/usr/bin/env python3
"""Диагностика связи с 1bit AI по слоям: ключ -> апстрим напрямую -> прокси.

Запуск:
    python scripts/Diagnose-1bitai.py

Показывает, на каком именно звене рвётся ответ нейронки, и печатает
сырое тело ответа при сбое (обрезанное), чтобы было видно «битый JSON».
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = os.environ.get("ONEBITAI_UPSTREAM", "https://api.1bitai.ru").rstrip("/")
PROXY = f"http://127.0.0.1:{os.environ.get('ONEBITAI_PROXY_PORT', '18765')}"
MODEL_RAW = os.environ.get("ONEBITAI_DIAG_MODEL", "qwen3-coder")
MODEL_UPSTREAM = os.environ.get("ONEBITAI_DIAG_MODEL_UPSTREAM", "ollama/qwen3-coder:latest")


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if sys.stdout.isatty() else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if sys.stdout.isatty() else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if sys.stdout.isatty() else s


def resolve_api_key() -> str:
    key = os.environ.get("ONEBITAI_API_KEY", "").strip()
    if key:
        return key
    local = ROOT / "opencode.local.json"
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8-sig"))
            raw = str(
                data.get("provider", {}).get("1bitai", {}).get("options", {}).get("apiKey", "")
            ).strip()
            if raw.startswith("{env:") and raw.endswith("}"):
                return os.environ.get(raw[5:-1].strip(), "").strip()
            if raw and raw != "local-proxy":
                return raw
        except (OSError, json.JSONDecodeError):
            pass
    return ""


def _ssl_ctx():
    if os.environ.get("ONEBITAI_VERIFY_SSL", "").strip().lower() in {"0", "false", "no"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _post(url: str, payload: dict, key: str | None) -> tuple[int, str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    kwargs = {"timeout": 120}
    ctx = _ssl_ctx()
    if ctx is not None:
        kwargs["context"] = ctx
    try:
        with urllib.request.urlopen(req, **kwargs) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.headers.get_content_type()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), "application/json"
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", ""


def _looks_like_chat_completion(body: str) -> bool:
    try:
        data = json.loads(body.lstrip("\ufeff").strip())
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    return isinstance(msg, dict) and (msg.get("content") or msg.get("tool_calls"))


def _verdict(status: int, body: str, ctype: str) -> tuple[bool, str]:
    if status == 0:
        return False, f"сеть/соединение: {body[:200]}"
    if status == 401 or status == 403:
        return False, "авторизация отклонена — проверьте ONEBITAI_API_KEY / права на модель"
    if status >= 500:
        return False, f"апстрим вернул {status} (сервер нейронки)"
    if status >= 400:
        return False, f"HTTP {status}: {body[:200]}"
    stripped = body.lstrip()
    if stripped.startswith("data:") or "event-stream" in (ctype or ""):
        return False, "апстрим прислал SSE-поток (stream не отключился) — это и есть «битый JSON» для OpenCode"
    if stripped[:1] not in "{[":
        return False, f"перед JSON мусор/BOM (первые байты: {body[:40]!r}) — «битый JSON»"
    if not _looks_like_chat_completion(body):
        return False, f"тело — не chat.completion: {body[:200]}"
    return True, "валидный ответ"


def main() -> int:
    print("=== Диагностика 1bit AI ===\n")
    ok_all = True

    # 1. Ключ
    key = resolve_api_key()
    if key:
        masked = key[:4] + "…" + key[-4:] if len(key) > 8 else "****"
        print(f"[1] API-ключ: {_green('найден')} ({masked})")
    else:
        print(f"[1] API-ключ: {_red('НЕ НАЙДЕН')}")
        print("    Задайте ONEBITAI_API_KEY или provider.1bitai.options.apiKey в opencode.local.json")
        return 1

    probe = {
        "model": MODEL_UPSTREAM,
        "messages": [{"role": "user", "content": "ответь одним словом: тест"}],
        "stream": False,
    }

    # 2. Апстрим напрямую (минуя прокси)
    print(f"\n[2] Апстрим напрямую: POST {UPSTREAM}/v1/chat/completions")
    status, body, ctype = _post(f"{UPSTREAM}/v1/chat/completions", probe, key)
    ok, why = _verdict(status, body, ctype)
    print(f"    HTTP {status} {ctype} -> {(_green if ok else _red)(why)}")
    if not ok:
        ok_all = False
        print(f"    {_yellow('Сырой ответ (до 400 символов):')}\n    {body[:400]}")
        print(
            "\n    Подсказки:\n"
            "    - SSE при stream=false → апстрим игнорирует флаг, лечится прокси (сборка из чанков)\n"
            "    - BOM/мусор → апстрим добавляет лог перед JSON, лечится прокси\n"
            "    - 401/403 → ключ или права; уточните у админа модель и доступ\n"
            "    - модель: апстрим ждёт именно " + MODEL_UPSTREAM + " (см. ONEBITAI_MODEL_MAP)\n"
        )

    # 3. Через прокси (то, что реально использует OpenCode)
    print(f"\n[3] Через локальный прокси: POST {PROXY}/v1/chat/completions (stream=true)")
    proxy_probe = dict(probe)
    proxy_probe["model"] = MODEL_RAW
    proxy_probe["stream"] = True
    status, body, ctype = _post(f"{PROXY}/v1/chat/completions", proxy_probe, "local-proxy")
    if status == 0:
        print(f"    {_red('Прокси не отвечает')} — запущен ли он? scripts\\Ensure-1bitaiProxy.ps1")
        print(f"    {body[:200]}")
        ok_all = False
    else:
        is_sse = "event-stream" in (ctype or "") and "chat.completion.chunk" in body and "[DONE]" in body
        has_payload = '"content"' in body or '"tool_calls"' in body
        has_error = '"error"' in body
        if is_sse and has_payload and not has_error:
            print(f"    HTTP {status} {ctype} → {_green('валидный SSE с ответом')}")
        elif has_error:
            print(f"    HTTP {status} {ctype} → {_red('прокси вернул ошибку в SSE')}")
            print(f"    {body[:300]}")
            ok_all = False
        else:
            print(f"    HTTP {status} {ctype} → {_red('неожиданный формат')}")
            print(f"    {body[:300]}")
            ok_all = False

    print("\n=== Итог ===")
    if ok_all:
        print(_green("Все слои отвечают. Если OpenCode всё равно молчит — проверьте baseURL "
                      "в opencode.json (должен указывать на прокси) и модель 1bitai/qwen3-coder."))
        return 0
    print(_red("Есть сбой на одном из слоёв — смотрите подсказки выше."))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
