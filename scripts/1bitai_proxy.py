#!/usr/bin/env python3
"""Локальный прокси к 1bit AI: отключает streaming для native tool_calls,
чинит «битые» ответы апстрима (BOM, мусор вокруг JSON, SSE вместо JSON)
и шлёт keepalive, чтобы OpenCode не отваливался по таймауту на долгой генерации."""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import threading
import time
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("ONEBITAI_UPSTREAM", "https://api.1bitai.ru").rstrip("/")
HOST = os.environ.get("ONEBITAI_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ONEBITAI_PROXY_PORT", "18765"))
KEEPALIVE_SECONDS = float(os.environ.get("ONEBITAI_KEEPALIVE_SECONDS", "15"))


def _resolve_api_key() -> str:
    key = os.environ.get("ONEBITAI_API_KEY", "").strip()
    if key:
        return key

    project_root = Path(__file__).resolve().parent.parent
    local_config = project_root / "opencode.local.json"
    if local_config.is_file():
        try:
            data = json.loads(local_config.read_text(encoding="utf-8-sig"))
            key = (
                data.get("provider", {})
                .get("1bitai", {})
                .get("options", {})
                .get("apiKey", "")
            )
            if isinstance(key, str) and key.strip():
                key = key.strip()
                if key.startswith("{env:") and key.endswith("}"):
                    env_name = key[5:-1].strip()
                    return os.environ.get(env_name, "").strip()
                return key
        except (json.JSONDecodeError, OSError, AttributeError):
            pass

    return ""


def _load_model_map() -> dict[str, str]:
    """Карта моделей: env ONEBITAI_MODEL_MAP (JSON) перекрывает дефолт."""
    default = {
        "qwen3-coder": "ollama/qwen3-coder:latest",
        "qwen3.5-35b": "ollama/qwen3.5:35b",
        "default": "ollama/qwen3-coder:latest",
    }
    raw = os.environ.get("ONEBITAI_MODEL_MAP", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                default.update({str(k): str(v) for k, v in data.items()})
        except json.JSONDecodeError:
            _log("ONEBITAI_MODEL_MAP не парсится как JSON — игнорирую")
    return default


ALLOWED_MODELS = _load_model_map()

DROP_PARAMS = (
    "response_format",
    "reasoning_effort",
    "reasoning",
    "modalities",
    "audio",
    "web_search_options",
    "prediction",
    "service_tier",
    "verbosity",
    "metadata",
    "store",
    "n",
    "logprobs",
    "logit_bias",
)
MAX_RETRIES = 3
# Эти статусы ретраить бессмысленно: ключ/права/маршрут не изменятся.
NO_RETRY_STATUSES = {400, 401, 403, 404, 405, 413, 422}


def _log(message: str) -> None:
    sys.stderr.write(f"[1bitai-proxy] {message}\n")


def _ssl_verify_enabled() -> bool:
    value = os.environ.get("ONEBITAI_VERIFY_SSL", "").strip().lower()
    if value in {"0", "false", "no"}:
        return False
    return True


def _ssl_context() -> ssl.SSLContext | None:
    if _ssl_verify_enabled():
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


# ---------------------------------------------------------------------------
# Лечение «битого JSON» от апстрима
# ---------------------------------------------------------------------------

_SSE_DATA_RE = re.compile(r"^data:\s*(.*)$", re.MULTILINE)


def _strip_junk(text: str) -> str:
    """Убирает BOM, нулевые байты и пробельный мусор вокруг полезной нагрузки."""
    return text.lstrip("\ufeff\u200b\x00 \t\r\n").rstrip("\x00 \t\r\n")


def _extract_first_json(text: str) -> dict[str, Any] | None:
    """Достаёт первый JSON-объект, даже если вокруг него мусор/логи/конкатенация."""
    text = _strip_junk(text)
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            payload, _end = decoder.raw_decode(text[idx:])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


def _assemble_sse_completion(text: str) -> dict[str, Any] | None:
    """Собирает chat.completion из SSE-потока (когда апстрим игнорирует stream=false)."""
    message: dict[str, Any] = {"role": "assistant", "content": ""}
    tool_calls: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    meta: dict[str, Any] = {}
    saw_chunk = False

    for match in _SSE_DATA_RE.finditer(text):
        data_raw = match.group(1).strip()
        if not data_raw or data_raw == "[DONE]":
            continue
        try:
            chunk = json.loads(data_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(chunk, dict):
            continue
        saw_chunk = True
        for key in ("id", "created", "model"):
            if chunk.get(key) and key not in meta:
                meta[key] = chunk[key]
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = choice.get("delta") or choice.get("message") or {}
        if not isinstance(delta, dict):
            delta = {}
        if delta.get("role"):
            message["role"] = delta["role"]
        content = delta.get("content")
        if isinstance(content, str):
            message["content"] += content
        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            index = int(tc.get("index", 0))
            slot = tool_calls.setdefault(
                index,
                {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
            )
            if tc.get("id"):
                slot["id"] = tc["id"]
            if tc.get("type"):
                slot["type"] = tc["type"]
            fn = tc.get("function") or {}
            if isinstance(fn, dict):
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if isinstance(fn.get("arguments"), str):
                    slot["function"]["arguments"] += fn["arguments"]
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]

    if not saw_chunk:
        return None
    if tool_calls:
        message["tool_calls"] = [tool_calls[k] for k in sorted(tool_calls)]
        if not message["content"]:
            message["content"] = None
    return {
        "id": meta.get("id", "sse-assembled"),
        "object": "chat.completion",
        "created": meta.get("created", int(time.time())),
        "model": meta.get("model", ""),
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason or ("tool_calls" if tool_calls else "stop"),
            }
        ],
    }


def _repair_chat_payload(payload: bytes, content_type: str) -> tuple[bytes, str, dict[str, Any] | None]:
    """Нормализует ответ chat/completions: BOM/мусор, SSE вместо JSON.

    Возвращает (payload, content_type, completion_dict_или_None)."""
    text = payload.decode("utf-8", "replace")

    looks_like_sse = "text/event-stream" in (content_type or "") or text.lstrip().startswith("data:")
    if looks_like_sse:
        completion = _assemble_sse_completion(text)
        if completion is not None:
            _log("апстрим вернул SSE при stream=false — собрал chat.completion из чанков")
            fixed = json.dumps(completion, ensure_ascii=False).encode("utf-8")
            return fixed, "application/json", completion

    completion = _extract_first_json(text)
    if completion is not None:
        fixed = json.dumps(completion, ensure_ascii=False).encode("utf-8")
        if fixed != payload.strip():
            _log("ответ апстрима содержал мусор вокруг JSON — нормализовал")
        return fixed, "application/json", completion

    return payload, content_type or "application/json", None


# ---------------------------------------------------------------------------
# Санация запроса (как в исходнике)
# ---------------------------------------------------------------------------

def _has_tool_history(messages: list[Any]) -> bool:
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "tool":
            return True
        if message.get("tool_calls"):
            return True
    return False


def _normalize_tool_definition(tool: Any, aggressive: bool) -> dict[str, Any] | None:
    if not isinstance(tool, dict):
        return None
    normalized = dict(tool)
    function = normalized.get("function")
    if not isinstance(function, dict):
        return normalized

    function = dict(function)
    function.pop("strict", None)
    parameters = function.get("parameters")
    if isinstance(parameters, dict):
        parameters = dict(parameters)
        parameters.pop("additionalProperties", None)
        parameters.pop("$schema", None)
        if aggressive:
            properties = parameters.get("properties")
            if isinstance(properties, dict):
                cleaned_props: dict[str, Any] = {}
                for name, prop in properties.items():
                    if isinstance(prop, dict):
                        prop = dict(prop)
                        prop.pop("additionalProperties", None)
                        prop.pop("strict", None)
                    cleaned_props[name] = prop
                parameters["properties"] = cleaned_props
        function["parameters"] = parameters
    normalized["function"] = function
    return normalized


def _sanitize_chat_data(data: dict[str, Any], aggressive: bool = False) -> dict[str, Any]:
    model = data.get("model")
    if isinstance(model, str):
        mapped = ALLOWED_MODELS.get(model.strip())
        if mapped:
            data["model"] = mapped
        elif model not in ALLOWED_MODELS.values() and not model.startswith("ollama/"):
            _log(f"подозрительная model={model!r}, подставляем {ALLOWED_MODELS['default']}")
            data["model"] = ALLOWED_MODELS["default"]

    for param in DROP_PARAMS:
        data.pop(param, None)

    tools = data.get("tools")
    if tools is not None and (not isinstance(tools, list) or not tools):
        data.pop("tools", None)
        data.pop("tool_choice", None)
    elif isinstance(tools, list):
        cleaned_tools = []
        for tool in tools:
            normalized = _normalize_tool_definition(tool, aggressive=aggressive)
            if normalized is not None:
                cleaned_tools.append(normalized)
        if cleaned_tools:
            data["tools"] = cleaned_tools
        else:
            data.pop("tools", None)
            data.pop("tool_choice", None)

    if aggressive:
        data.pop("tool_choice", None)

    messages = data.get("messages")
    if isinstance(messages, list) and _has_tool_history(messages) and not data.get("tools"):
        data["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "No-op tool for LiteLLM compatibility when history contains tool calls.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        _log("добавлен dummy tools= для истории с tool_calls")

    return data


def _is_upstream_failure(status: int, payload: bytes, completion: dict[str, Any] | None) -> bool:
    if status >= 400:
        return True

    data = completion
    text = ""
    if data is None:
        text = payload.decode("utf-8", "replace")
        try:
            data = json.loads(_strip_junk(text))
        except json.JSONDecodeError:
            return "Operation not allowed" in text

    if isinstance(data.get("error"), dict):
        return True

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        if not isinstance(message, dict):
            message = {}
        if message.get("tool_calls"):
            return False
        content = message.get("content")
        if isinstance(content, str) and "Operation not allowed" in content:
            stripped = content.strip()
            if stripped.startswith("{") or len(stripped) < 200:
                return True
        # Валидный ответ ассистента — успех; маркеры дальше не проверяем,
        # иначе ловим ложные срабатывания на словах вроде "content filtering" в тексте ответа.
        if content or message.get("role") == "assistant":
            return False

    if not text:
        text = payload.decode("utf-8", "replace")
    markers = (
        "Operation not allowed",
        "llm_call_failed",
        "team_model_access_denied",
        "does not support thinking",
        "content filtering",
        "content_filter",
    )
    return any(marker in text for marker in markers)


def _forward(method: str, path: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes, str]:
    url = f"{UPSTREAM}{path}"
    req_headers = {
        "Content-Type": headers.get("Content-Type", "application/json"),
        "Accept": headers.get("Accept", "application/json"),
    }
    api_key = _resolve_api_key()
    if api_key:
        req_headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    open_kwargs: dict[str, Any] = {"timeout": 300}
    ssl_context = _ssl_context()
    if ssl_context is not None:
        open_kwargs["context"] = ssl_context
    try:
        with urllib.request.urlopen(request, **open_kwargs) as response:
            return response.status, response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as error:
        payload = error.read()
        return error.code, payload, error.headers.get_content_type() if error.headers else "application/json"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        body_err = json.dumps(
            {"error": {"message": f"proxy: upstream недоступен: {error}", "type": "upstream_unreachable"}},
            ensure_ascii=False,
        ).encode("utf-8")
        return 502, body_err, "application/json"


def _build_chat_body(raw: bytes, aggressive: bool) -> tuple[bytes, bool]:
    """Готовит тело chat/completions для upstream и возвращает флаг stream клиента."""
    try:
        data: dict[str, Any] = json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw, False

    client_stream = bool(data.get("stream"))
    if client_stream:
        data["stream"] = False
    data.pop("stream_options", None)
    data = _sanitize_chat_data(data, aggressive=aggressive)
    return json.dumps(data, ensure_ascii=False).encode("utf-8"), client_stream


def _forward_with_retry(
    method: str,
    path: str,
    body: bytes | None,
    headers: dict[str, str],
    raw_chat_body: bytes | None = None,
) -> tuple[int, bytes, str, dict[str, Any] | None]:
    is_chat = raw_chat_body is not None
    last: tuple[int, bytes, str, dict[str, Any] | None] = (502, b"", "application/json", None)
    for attempt in range(1, MAX_RETRIES + 1):
        payload_body = body
        if is_chat:
            payload_body, _ = _build_chat_body(raw_chat_body, aggressive=(attempt > 1))
        status, payload, content_type = _forward(method, path, payload_body, headers)

        completion: dict[str, Any] | None = None
        if is_chat and status == 200:
            payload, content_type, completion = _repair_chat_payload(payload, content_type)

        last = (status, payload, content_type, completion)
        if not _is_upstream_failure(status, payload, completion):
            return last
        preview = payload.decode("utf-8", "replace")[:200]
        _log(
            f"upstream fail attempt {attempt}/{MAX_RETRIES} "
            f"aggressive={attempt > 1}: HTTP {status} {preview}"
        )
        if status in NO_RETRY_STATUSES:
            _log(f"HTTP {status} — ретраи не помогут, отдаю клиенту как есть")
            return last
        if attempt < MAX_RETRIES:
            time.sleep(0.8 * attempt)
    return last


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _completion_to_sse(completion: dict[str, Any]) -> bytes:
    """Оборачивает chat.completion в SSE: OpenCode ждёт event-stream при stream=true."""
    base: dict[str, Any] = {
        "id": completion.get("id", ""),
        "object": "chat.completion.chunk",
        "created": completion.get("created", 0),
        "model": completion.get("model", ""),
    }
    choices = completion.get("choices") or [{}]
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    finish_reason = choice.get("finish_reason")

    parts: list[str] = []
    role = message.get("role") or "assistant"
    parts.append(
        _sse_event(
            {
                **base,
                "choices": [{"index": 0, "delta": {"role": role}, "finish_reason": None}],
            }
        )
    )

    content = message.get("content")
    if isinstance(content, str) and content:
        parts.append(
            _sse_event(
                {
                    **base,
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }
            )
        )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for index, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, dict):
                continue
            parts.append(
                _sse_event(
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": index,
                                            "id": tool_call.get("id"),
                                            "type": tool_call.get("type", "function"),
                                            "function": tool_call.get("function") or {},
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                )
            )

    parts.append(
        _sse_event(
            {
                **base,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            }
        )
    )
    parts.append("data: [DONE]\n\n")
    return "".join(parts).encode("utf-8")


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"[1bitai-proxy] {self.address_string()} - {format % args}\n")

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type or "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def _read_body(self) -> bytes | None:
        """Читает тело запроса; chunked не поддерживаем — честно отвечаем 411."""
        if (self.headers.get("Transfer-Encoding") or "").lower() == "chunked":
            self._send(
                411,
                json.dumps(
                    {"error": {"message": "proxy: chunked body не поддерживается, нужен Content-Length"}},
                    ensure_ascii=False,
                ).encode("utf-8"),
                "application/json",
            )
            return None
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def do_GET(self) -> None:
        status, payload, content_type, _ = _forward_with_retry("GET", self.path, None, dict(self.headers))
        self._send(status, payload, content_type)

    def do_POST(self) -> None:
        raw_body = self._read_body()
        if raw_body is None:
            return
        is_chat = self.path.startswith("/v1/chat/completions") or self.path == "/chat/completions"

        if not is_chat:
            status, payload, content_type, _ = _forward_with_retry(
                "POST", self.path, raw_body, dict(self.headers)
            )
            self._send(status, payload, content_type)
            return

        _, client_stream = _build_chat_body(raw_body, aggressive=False)

        if not client_stream:
            status, payload, content_type, _ = _forward_with_retry(
                "POST", self.path, None, dict(self.headers), raw_chat_body=raw_body
            )
            self._send(status, payload, content_type)
            return

        # Клиент просит stream: сразу открываем SSE и шлём keepalive-комментарии,
        # пока ждём полного ответа от апстрима — иначе OpenCode/браузер рвёт соединение.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        result: dict[str, Any] = {}
        done = threading.Event()

        def _worker() -> None:
            try:
                result["value"] = _forward_with_retry(
                    "POST", self.path, None, dict(self.headers), raw_chat_body=raw_body
                )
            finally:
                done.set()

        threading.Thread(target=_worker, daemon=True).start()
        try:
            while not done.wait(KEEPALIVE_SECONDS):
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            _log("клиент закрыл соединение во время ожидания апстрима")
            return

        status, payload, content_type, completion = result.get(
            "value", (502, b"", "application/json", None)
        )

        if status == 200 and completion is None:
            try:
                candidate = json.loads(payload.decode("utf-8-sig"))
                if isinstance(candidate, dict) and candidate.get("object") == "chat.completion":
                    completion = candidate
            except (json.JSONDecodeError, UnicodeDecodeError):
                completion = None

        try:
            if status == 200 and isinstance(completion, dict) and completion.get("choices"):
                self.wfile.write(_completion_to_sse(completion))
            else:
                # Ошибку тоже отдаём в рамках открытого SSE, иначе клиент повиснет.
                err_text = payload.decode("utf-8", "replace")[:1000]
                self.wfile.write(
                    _sse_event(
                        {"error": {"message": f"upstream HTTP {status}: {err_text}", "code": status}}
                    ).encode("utf-8")
                )
                self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            _log("клиент закрыл соединение при отдаче ответа")


def main() -> int:
    if not _resolve_api_key():
        print("ONEBITAI_API_KEY не задан", file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((HOST, PORT), ProxyHandler)
    print(f"1bit AI proxy: http://{HOST}:{PORT}/v1 -> {UPSTREAM}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
