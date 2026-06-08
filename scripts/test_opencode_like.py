#!/usr/bin/env python3
"""Имитация запроса OpenCode: много tools, история с tool result."""

from __future__ import annotations

import json
import os
import urllib.request

KEY = os.environ.get("ONEBITAI_API_KEY", "")
BASE = "http://127.0.0.1:18765/v1/chat/completions"

tools = [
    {
        "type": "function",
        "function": {
            "name": f"tool_{index}",
            "description": "desc",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        },
    }
    for index in range(25)
]

welcome_result = {
    "formatted_user": "Привет! Чем помочь?",
    "question": {
        "title": "Режим",
        "prompt": "Есть доступ к базе?",
        "options": ["live", "offline", "research"],
    },
}

messages = [
    {"role": "system", "content": "You are 1c analyst. " * 50},
    {"role": "user", "content": "привет"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "onec_welcome",
                    "arguments": json.dumps({"first_user_message": "привет"}, ensure_ascii=False),
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": json.dumps(welcome_result, ensure_ascii=False),
    },
]

body = {
    "model": "ollama/qwen3-coder:latest",
    "messages": messages,
    "tools": tools,
    "tool_choice": "auto",
    "stream": True,
}

request = urllib.request.Request(
    BASE,
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=120) as response:
    text = response.read().decode("utf-8", "replace")
    print("status", response.status)
    print("operation_not_allowed", "Operation not allowed" in text)
    print("has_tool_calls", "tool_calls" in text)
    print("has_content", '"content"' in text)
    print(text[:800])
