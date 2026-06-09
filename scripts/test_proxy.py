#!/usr/bin/env python3
"""Быстрая проверка локального прокси 1bit AI."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:18765"


def _load_api_key() -> str:
    key = os.environ.get("ONEBITAI_API_KEY", "").strip()
    if key:
        return key
    local = Path(__file__).resolve().parent.parent / "opencode.local.json"
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            key = str(data.get("provider", {}).get("1bitai", {}).get("options", {}).get("apiKey", "")).strip()
            if key and not key.startswith("{env:"):
                return key
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return ""


def main() -> int:
    key = _load_api_key()
    if not key:
        print("FAIL: ONEBITAI_API_KEY не задан")
        return 1

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/v1/models", headers=headers), timeout=10
    ) as response:
        models = json.loads(response.read())["data"]
    print(f"OK models: {len(models)} ({models[0]['id']})")

    checks = [
        (
            "stream_text",
            {
                "model": "ollama/qwen3-coder:latest",
                "messages": [{"role": "user", "content": "ответь одним словом: да"}],
                "stream": True,
            },
            lambda body, ctype: ctype.startswith("text/event-stream")
            and "chat.completion.chunk" in body
            and "[DONE]" in body,
        ),
        (
            "stream_tools",
            {
                "model": "ollama/qwen3-coder:latest",
                "messages": [{"role": "user", "content": "привет"}],
                "stream": True,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "onec_welcome",
                            "description": "Welcome",
                            "parameters": {
                                "type": "object",
                                "properties": {"first_user_message": {"type": "string"}},
                                "required": ["first_user_message"],
                            },
                        },
                    }
                ],
                "tool_choice": "auto",
            },
            lambda body, ctype: ctype.startswith("text/event-stream")
            and "tool_calls" in body
            and "[DONE]" in body,
        ),
    ]

    for name, payload, validator in checks:
        started = time.time()
        request = urllib.request.Request(
            f"{BASE}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            ctype = response.headers.get("Content-Type", "")
            body = raw.decode("utf-8", "replace")
            elapsed = time.time() - started

        if validator(body, ctype):
            print(f"OK {name}: {elapsed:.2f}s, {ctype}")
        else:
            print(f"FAIL {name}: {elapsed:.2f}s, {ctype}")
            print(body[:500])
            return 1

    # История с tool_calls без tools= (типичная причина Operation not allowed у LiteLLM)
    history_body = {
        "model": "ollama/qwen3-coder:latest",
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "onec_welcome",
                            "arguments": json.dumps({"first_user_message": "hi"}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
            {"role": "user", "content": "continue"},
        ],
        "stream": True,
    }
    request = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=json.dumps(history_body).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8", "replace")
        if "Operation not allowed" in body:
            print("FAIL history_without_tools: Operation not allowed")
            print(body[:500])
            return 1
        print("OK history_without_tools")

    empty_tools = {
        "model": "ollama/qwen3-coder:latest",
        "messages": [{"role": "user", "content": "да"}],
        "stream": True,
        "tools": [],
    }
    request = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=json.dumps(empty_tools).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8", "replace")
        if "Operation not allowed" in body:
            print("FAIL empty_tools: Operation not allowed")
            print(body[:500])
            return 1
        print("OK empty_tools")

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
