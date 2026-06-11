"""MVP оркестратор для 1C Bridge Agent: очередь jobs, poll/result."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from collections import deque
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(title="1C Bridge Orchestrator", version="0.1.0")

# Завершённые задачи держим ограниченное время, иначе _job_store растёт без предела.
JOB_RETENTION_SECONDS = 3600.0
JOB_STORE_MAX = 5000


def _purge_old_jobs_locked() -> None:
    """Удаляет завершённые задачи старше TTL. Вызывать под _lock."""
    now = time.time()
    stale = [
        jid
        for jid, job in _job_store.items()
        if job.get("status") in {"ok", "error", "failed"}
        and now - float(job.get("finished_at") or job.get("created_at") or now) > JOB_RETENTION_SECONDS
    ]
    for jid in stale:
        _job_store.pop(jid, None)
    # Жёсткий предел на случай всплеска: режем самые старые.
    if len(_job_store) > JOB_STORE_MAX:
        for jid, _ in sorted(_job_store.items(), key=lambda kv: kv[1].get("created_at", 0))[
            : len(_job_store) - JOB_STORE_MAX
        ]:
            _job_store.pop(jid, None)

_lock = threading.Lock()
_bridges: dict[str, dict[str, Any]] = {}
_job_queues: dict[str, deque[dict[str, Any]]] = {}
_job_store: dict[str, dict[str, Any]] = {}


class BridgeRegisterRequest(BaseModel):
    bridge_id: str = Field(min_length=1, max_length=128)
    bridge_token: str = Field(min_length=8, max_length=256)
    info_base_label: str = ""


class EnqueueRequest(BaseModel):
    bridge_id: str = Field(min_length=1, max_length=128)
    bridge_token: str = Field(min_length=1, max_length=256)
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class JobResultRequest(BaseModel):
    job_id: str
    bridge_id: str
    bridge_token: str
    status: str = "ok"
    result: dict[str, Any] | None = None
    error: str | None = None


def _verify_bridge(bridge_id: str, bridge_token: str) -> None:
    with _lock:
        bridge = _bridges.get(bridge_id)
    expected = bridge.get("token") if bridge else ""
    # secrets.compare_digest — защита от timing-атак по токену.
    if not bridge or not secrets.compare_digest(str(expected), str(bridge_token)):
        raise HTTPException(status_code=401, detail="Неверный bridge_id или bridge_token")


def _touch_bridge(bridge_id: str) -> None:
    with _lock:
        if bridge_id in _bridges:
            _bridges[bridge_id]["last_poll_at"] = time.time()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/bridge/register")
def register_bridge(body: BridgeRegisterRequest) -> dict[str, Any]:
    with _lock:
        existing = _bridges.get(body.bridge_id)
        if existing and existing.get("token") != body.bridge_token:
            raise HTTPException(status_code=409, detail="bridge_id уже занят другим token")
        _bridges[body.bridge_id] = {
            "token": body.bridge_token,
            "info_base_label": body.info_base_label,
            "registered_at": time.time(),
            "last_poll_at": None,
        }
        _job_queues.setdefault(body.bridge_id, deque())
    return {"status": "registered", "bridge_id": body.bridge_id}


@app.get("/api/bridge/poll")
def poll_job(
    bridge_id: str = Query(..., min_length=1),
    bridge_token: str = Query("", min_length=0),
    wait_sec: int = Query(25, ge=0, le=60),
    x_bridge_token: str = Header(default=""),
) -> dict[str, Any]:
    # Предпочитаем токен из заголовка: query-string оседает в логах прокси.
    token = x_bridge_token or bridge_token
    _verify_bridge(bridge_id, token)

    deadline = time.time() + wait_sec
    while True:
        _touch_bridge(bridge_id)
        with _lock:
            queue = _job_queues.get(bridge_id)
            if queue and len(queue) > 0:
                job = queue.popleft()
                job["status"] = "running"
                job["started_at"] = time.time()
                _job_store[job["job_id"]] = job
                return {"job": job}
        if wait_sec <= 0 or time.time() >= deadline:
            return {"job": None}
        time.sleep(0.5)


@app.post("/api/bridge/result")
def submit_result(body: JobResultRequest) -> dict[str, Any]:
    _verify_bridge(body.bridge_id, body.bridge_token)
    with _lock:
        job = _job_store.get(body.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job_id не найден")
        if job.get("bridge_id") != body.bridge_id:
            raise HTTPException(status_code=403, detail="job принадлежит другому bridge_id")
        job["status"] = body.status
        job["finished_at"] = time.time()
        job["result"] = body.result
        job["error"] = body.error
    return {"status": "accepted", "job_id": body.job_id}


@app.post("/api/bridge/enqueue")
def enqueue_job(body: EnqueueRequest) -> dict[str, Any]:
    _verify_bridge(body.bridge_id, body.bridge_token)
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "bridge_id": body.bridge_id,
        "tool": body.tool,
        "arguments": body.arguments,
        "status": "pending",
        "created_at": time.time(),
    }
    with _lock:
        _job_queues.setdefault(body.bridge_id, deque()).append(job)
        _job_store[job_id] = job
        _purge_old_jobs_locked()
    return {"status": "queued", "job_id": job_id, "job": job}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        job = _job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job не найден")
    return job


@app.on_event("startup")
def seed_demo_bridge() -> None:
    """Демо-мост demotrd для локального теста (token из example-конфига)."""
    demo_token = "change-me-local-demo-token"
    with _lock:
        _bridges.setdefault(
            "demotrd",
            {
                "token": demo_token,
                "info_base_label": r"C:\Users\aaposmetev\Documents\1C\DemoTrd",
                "registered_at": time.time(),
                "last_poll_at": None,
            },
        )
        _job_queues.setdefault("demotrd", deque())


@app.get("/api/bridges")
def list_bridges() -> dict[str, Any]:
    with _lock:
        items = []
        for bridge_id, data in _bridges.items():
            queue_len = len(_job_queues.get(bridge_id, deque()))
            items.append(
                {
                    "bridge_id": bridge_id,
                    "info_base_label": data.get("info_base_label", ""),
                    "last_poll_at": data.get("last_poll_at"),
                    "pending_jobs": queue_len,
                }
            )
    return {"bridges": items}
