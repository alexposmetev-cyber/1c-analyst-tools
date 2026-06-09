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
            if isinstance(key, str) and key.strip():
                key = key.strip()
                if key.startswith("{env:") and key.endswith("}"):
                    env_name = key[5:-1].strip()
                    return os.environ.get(env_name, "").strip()
                return key
        except (json.JSONDecodeError, OSError, AttributeError):
            pass

    return ""


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
    "store",
    "n",
    "logprobs",
    "logit_bias",
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
            _log(f"подозрительная model={model!r}, подставляем ollama/qwen3-coder:latest")
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


def _is_upstream_failure(status: int, payload: bytes) -> bool:
    if status >= 400:
        return True
    text = payload.decode("utf-8", "replace")
    try:
        data = json.loads(text)
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
        if content or message.get("role") == "assistant":
            return False

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
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as error:
        payload = error.read()
        return error.code, payload, error.headers.get_content_type() if error.headers else "application/json"


def _build_chat_body(raw: bytes, aggressive: bool) -> tuple[bytes, bool]:
    """Готовит тело chat/completions для upstream и возвращает флаг stream клиента."""
    try:
        data: dict[str, Any] = json.loads(raw.decode("utf-8"))
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
) -> tuple[int, bytes, str]:
    last: tuple[int, bytes, str] = (502, b"", "application/json")
    for attempt in range(1, MAX_RETRIES + 1):
        payload_body = body
        if raw_chat_body is not None:
            payload_body, _ = _build_chat_body(raw_chat_body, aggressive=(attempt > 1))
        status, payload, content_type = _forward(method, path, payload_body, headers)
        last = (status, payload, content_type)
        if not _is_upstream_failure(status, payload):
            return status, payload, content_type
        preview = payload.decode("utf-8", "replace")[:200]
        _log(
            f"upstream fail attempt {attempt}/{MAX_RETRIES} "
            f"aggressive={attempt > 1}: HTTP {status} {preview}"
        )
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
        raw_body = self.rfile.read(length) if length else b""
        client_stream = False
        is_chat = self.path.startswith("/v1/chat/completions") or self.path == "/chat/completions"
        if is_chat:
            _, client_stream = _build_chat_body(raw_body, aggressive=False)
            status, payload, content_type = _forward_with_retry(
                "POST",
                self.path,
                None,
                dict(self.headers),
                raw_chat_body=raw_body,
            )
        else:
            status, payload, content_type = _forward_with_retry(
                "POST",
                self.path,
                raw_body,
                dict(self.headers),
            )
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
