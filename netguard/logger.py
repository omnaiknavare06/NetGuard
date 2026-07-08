from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
INCIDENT_DIR = BASE_DIR / "incidents"
LOG_FILE = LOG_DIR / "system.log"

_LOCK = Lock()

COLORS = {
    "SYSTEM": "\033[90m",
    "CLIENT": "\033[36m",
    "MONITOR": "\033[33m",
    "AI": "\033[34m",
    "EXECUTOR": "\033[32m",
    "PIPELINE": "\033[35m",
    "CAPACITY": "\033[31m",
    "LATENCY": "\033[93m",
    "TASK": "\033[96m",
    "INCIDENT": "\033[91m",
}
RESET = "\033[0m"


def ensure_storage() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.touch(exist_ok=True)


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(category: str, message: str) -> str:
    ensure_storage()
    category = (category or "SYSTEM").upper()[:8]
    line = f"[{_timestamp()}] [{category:<8}] {message}"
    with _LOCK:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    color = COLORS.get(category, "")
    print(f"{color}{line}{RESET}")
    return line


def read_logs(limit: int = 200) -> list[str]:
    ensure_storage()
    limit = max(1, min(int(limit or 200), 1000))
    with _LOCK:
        with LOG_FILE.open("r", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in deque(handle, maxlen=limit)]


def save_incident(incident: dict[str, Any]) -> str:
    ensure_storage()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"incident_{stamp}.json"
    path = INCIDENT_DIR / filename
    with _LOCK:
        path.write_text(json.dumps(incident, indent=2), encoding="utf-8")
    log("INCIDENT", f"Saved incident report to {filename}")
    return filename


def load_incidents(limit: int = 20) -> list[dict[str, Any]]:
    ensure_storage()
    limit = max(1, min(int(limit or 20), 100))
    files = sorted(INCIDENT_DIR.glob("incident_*.json"), reverse=True)[:limit]
    incidents: list[dict[str, Any]] = []
    for path in files:
        try:
            incidents.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            log("INCIDENT", f"Skipped unreadable incident file {path.name}")
    return incidents


def clear_incidents() -> int:
    ensure_storage()
    removed = 0
    with _LOCK:
        for path in INCIDENT_DIR.glob("incident_*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                log("INCIDENT", f"Could not remove incident file {path.name}")
    return removed


def incident_stats() -> dict[str, Any]:
    ensure_storage()
    files = sorted(INCIDENT_DIR.glob("incident_*.json"), reverse=True)
    return {
        "total": len(files),
        "latest": files[0].name if files else None,
    }
