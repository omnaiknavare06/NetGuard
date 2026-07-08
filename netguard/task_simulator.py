from __future__ import annotations

import random
import time
from typing import Any

from state_manager import StateManager

TASK_PROFILES = {
    "login": {"cpu": 3.0, "ram": 1.0, "base_ms": 80, "jitter_ms": 60, "payload_bytes": 256},
    "logout": {"cpu": 1.0, "ram": 0.0, "base_ms": 20, "jitter_ms": 10, "payload_bytes": 64},
    "db_query": {"cpu": 18.0, "ram": 12.0, "base_ms": 300, "jitter_ms": 400, "payload_bytes": 512},
    "file_upload": {"cpu": 8.0, "ram": 25.0, "base_ms": 400, "jitter_ms": 600, "payload_bytes": 5000000},
    "file_download": {"cpu": 6.0, "ram": 15.0, "base_ms": 250, "jitter_ms": 300, "payload_bytes": 500000},
    "compute": {"cpu": 35.0, "ram": 8.0, "base_ms": 800, "jitter_ms": 1200, "payload_bytes": 1024},
    "search": {"cpu": 12.0, "ram": 6.0, "base_ms": 200, "jitter_ms": 300, "payload_bytes": 384},
    "stream": {"cpu": 10.0, "ram": 20.0, "base_ms": 600, "jitter_ms": 800, "payload_bytes": 2000000},
    "bulk_process": {"cpu": 40.0, "ram": 30.0, "base_ms": 1200, "jitter_ms": 2000, "payload_bytes": 10000000},
    "heartbeat": {"cpu": 0.5, "ram": 0.0, "base_ms": 10, "jitter_ms": 5, "payload_bytes": 64},
}


def _result_for(task_name: str, login_success: bool) -> dict[str, Any]:
    if task_name == "login":
        return {"authenticated": login_success, "message": "Access granted." if login_success else "Invalid credentials."}
    if task_name == "logout":
        return {"terminated": True}
    if task_name == "db_query":
        return {
            "rows_returned": random.randint(8, 42),
            "query_plan": random.choice(["Index Scan on users", "Hash Join on orders", "Bitmap Heap Scan on logs"]),
        }
    if task_name == "file_upload":
        return {"stored_mb": 5, "chunk_count": 20}
    if task_name == "file_download":
        return {"bytes_sent": 500000, "cache": random.choice(["hit", "miss"])}
    if task_name == "compute":
        return {"job": "matrix_transform", "iterations": random.randint(2000, 8000)}
    if task_name == "search":
        return {"hits": random.randint(3, 120), "top_document": "network-alert-runbook.md"}
    if task_name == "stream":
        return {"stream_seconds": random.randint(20, 90), "quality": random.choice(["720p", "1080p"])}
    if task_name == "bulk_process":
        return {"records_processed": random.randint(700, 2500), "batch_status": "complete"}
    return {"alive": True}


def process_task(
    state: StateManager,
    task_name: str,
    client_id: str,
    *,
    login_success: bool = True,
) -> dict[str, Any]:
    if task_name not in TASK_PROFILES:
        raise ValueError(f"Unknown task: {task_name}")

    profile = TASK_PROFILES[task_name]
    snapshot = state.snapshot()
    active_sessions = snapshot["capacity"]["active_sessions"]
    overload_factor = 1.0
    if active_sessions > state.MAX_NORMAL:
        overload_factor += (active_sessions - state.MAX_NORMAL) * 0.3

    delay_ms = (profile["base_ms"] + random.randint(0, profile["jitter_ms"])) * overload_factor
    state.set_current_task(client_id, task_name)
    start = time.perf_counter()
    time.sleep(delay_ms / 1000)

    should_fail = overload_factor > 1.8 and task_name != "heartbeat" and random.random() < 0.15
    if task_name == "login" and not login_success:
        state.add_failed_logins(1)

    state.update_resources(cpu_delta=profile["cpu"], ram_delta=profile["ram"] * 0.3)
    state.record_request(profile["payload_bytes"])

    latency_ms = (time.perf_counter() - start) * 1000
    if should_fail:
        state.record_task(client_id, task_name, latency_ms, success=False, result_summary="task error under overload")
        return {
            "status": "error",
            "task": task_name,
            "latency_ms": round(latency_ms, 1),
            "overload_factor": round(overload_factor, 2),
            "error": "Simulated server overload caused this task to fail.",
        }

    result = _result_for(task_name, login_success)
    summary = result.get("message") or result.get("job") or result.get("batch_status") or "ok"
    state.record_task(client_id, task_name, latency_ms, success=login_success or task_name != "login", result_summary=str(summary))
    return {
        "status": "ok" if login_success or task_name != "login" else "denied",
        "task": task_name,
        "latency_ms": round(latency_ms, 1),
        "overload_factor": round(overload_factor, 2),
        "result": result,
    }
