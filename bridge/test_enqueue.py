#!/usr/bin/env python3
"""Тест bridge: ping и execute_query (UTF-8)."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8787"
BRIDGE_ID = "demotrd"
TOKEN = "change-me-local-demo-token"


def post(path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_job(job_id: str, timeout_sec: int = 90) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        job = get(f"/api/jobs/{job_id}")
        if job.get("status") in ("ok", "error"):
            return job
        time.sleep(2)
    raise TimeoutError(f"job {job_id} timeout")


def enqueue(tool: str, arguments: dict) -> dict:
    return post(
        "/api/bridge/enqueue",
        {
            "bridge_id": BRIDGE_ID,
            "bridge_token": TOKEN,
            "tool": tool,
            "arguments": arguments,
        },
    )


def main() -> int:
    print("=== ping ===")
    ping_job = enqueue("ping", {})
    print("job_id:", ping_job["job_id"])
    ping_result = wait_job(ping_job["job_id"])
    print(json.dumps(ping_result, ensure_ascii=False, indent=2))
    if ping_result.get("status") != "ok":
        return 1

    print("=== execute_query ===")
    query = (
        "\u0412\u042b\u0411\u0420\u0410\u0422\u042c \u041f\u0415\u0420\u0412\u042b\u0415 3 "
        "\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u041a\u0410\u041a \u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 "
        "\u0418\u0417 \u0421\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a.\u041a\u043e\u043d\u0442\u0440\u0430\u0433\u0435\u043d\u0442\u044b"
    )
    query_job = enqueue("execute_query", {"query": query, "max_rows": 10})
    print("job_id:", query_job["job_id"])
    query_result = wait_job(query_job["job_id"])
    print(json.dumps(query_result, ensure_ascii=False, indent=2))
    return 0 if query_result.get("status") == "ok" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Оркестратор недоступен: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
