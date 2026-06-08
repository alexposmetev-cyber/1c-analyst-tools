#!/usr/bin/env python3
"""Локальный прокси к 1bit AI: принудительно отключает streaming для native tool_calls."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

UPSTREAM = os.environ.get("ONEBITAI_UPSTREAM", "https://api.1bitai.ru").rstrip("/")
HOST = os.environ.get("ONEBITAI_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("ONEBITAI_PROXY_PORT", "18765"))


def _resolve_api_key() -> str:
    key = os.environ.get("ONEBITAI_API_KEY", "").strip()
    if key:
        return key

    project_root = Path(__file__).resolve().parent.parent
    local_config = project_root / "opencode.local.json"
    if local_config.is_file():
        try:
            data = json.loads(local_config.read_text(encoding="utf-8"))
            key = (
                data.get("provider", {})
                .get("1bitai", {})
                .get("options", {})
                .get("apiKey", "")
            )
            if isinstance(key, str) and key.strip() and not key.strip().startswith("{env:"):
                return key.strip()
        except (json.JSONDecodeError, OSError, AttributeError):
            pass

    return ""


API_KEY = _resolve_api_key()

ALLOWED_MODELS = {
    "qwen3-coder": "ollama/qwen3-coder:latest",
    "qwen3.5-35b": "ollama/qwen3.5:35b",
    "default": "ollama/qwen3-coder:latest",
}
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
)
MAX_RETRIES = 3


def _log(message: str) -> None:
    sys.stderr.write(f"[1bitai-proxy] {message}\n")


def _has_tool_history(messages: list[Any]) -> bool:
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "tool":
            return True
        if message.get("tool_calls"):
            return True
    return False


def _sanitize_chat_data(data: dict[str, Any]) -> dict[str, Any]:
    model = data.get("model")
    if isinstance(model, str):
        mapped = ALLOWED_MODELS.get(model.strip())
        if mapped:
            data["model"] = mapped
        elif model not in ALLOWED_MODELS.values() and not model.startswith("ollama/"):
            _log(f"подозрительная model={model!r}, подставляем ollama/qwen3-coder:latest")
            data["model"] = ALLOWED_MODELS["default"]

    for param in DROP_PARAMS:
        data.pop(param, None)

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


def _is_upstream_failure(status: int, payload: bytes) -> bool:
    if status >= 400:
        return True
    text = payload.decode("utf-8", "replace")
    markers = (
        "Operation not allowed",
        "llm_call_failed",
        "team_model_access_denied",
        "does not support thinking",
    )
    return any(marker in text for marker in markers)


def _forward(method: str, path: str, body: bytes | None, headers: dict[str, str]) -> tuple[int, bytes, str]:
    url = f"{UPSTREAM}{path}"
    req_headers = {
        "Content-Type": headers.get("Content-Type", "application/json"),
        "Accept": headers.get("Accept", "application/json"),
    }
    if API_KEY:
        req_headers["Authorization"] = f"Bearer {API_KEY}"

    request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as error:
        payload = error.read()
        return error.code, payload, error.headers.get_content_type() if error.headers else "application/json"


def _forward_with_retry(
    method: str, path: str, body: bytes | None, headers: dict[str, str]
) -> tuple[int, bytes, str]:
    last: tuple[int, bytes, str] = (502, b"", "application/json")
    for attempt in range(1, MAX_RETRIES + 1):
        status, payload, content_type = _forward(method, path, body, headers)
        last = (status, payload, content_type)
        if not _is_upstream_failure(status, payload):
            return status, payload, content_type
        preview = payload.decode("utf-8", "replace")[:200]
        _log(f"upstream fail attempt {attempt}/{MAX_RETRIES}: HTTP {status} {preview}")
        if attempt < MAX_RETRIES:
            time.sleep(0.8 * attempt)
    return last


def _parse_chat_body(raw: bytes) -> tuple[bytes, bool]:
    """Возвращает тело для upstream и флаг stream у клиента."""
    try:
        data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw, False

    client_stream = bool(data.get("stream"))
    if client_stream:
        data["stream"] = False
    data.pop("stream_options", None)
    data = _sanitize_chat_data(data)
    return json.dumps(data, ensure_ascii=False).encode("utf-8"), client_stream


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
    choice = completion["choices"][0]
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

    def do_GET(self) -> None:
        status, payload, content_type = _forward_with_retry("GET", self.path, None, dict(self.headers))
        self._send(status, payload, content_type)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        client_stream = False
        if self.path.startswith("/v1/chat/completions") or self.path == "/chat/completions":
            body, client_stream = _parse_chat_body(body)
        status, payload, content_type = _forward_with_retry("POST", self.path, body, dict(self.headers))
        if (
            client_stream
            and status == 200
            and (self.path.startswith("/v1/chat/completions") or self.path == "/chat/completions")
        ):
            try:
                completion = json.loads(payload.decode("utf-8"))
                if completion.get("object") == "chat.completion":
                    payload = _completion_to_sse(completion)
                    content_type = "text/event-stream; charset=utf-8"
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, IndexError, TypeError):
                pass
        self._send(status, payload, content_type)


def main() -> int:
    if not API_KEY:
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
