from __future__ import annotations

import platform
import shlex
import subprocess
from typing import Any

from logger import log

WINDOWS = platform.system().lower().startswith("win")

COMMANDS = {
    "ping": {"windows": ["ping", "-n", "4", "{target}"], "unix": ["ping", "-c", "4", "{target}"]},
    "netstat": {"windows": ["netstat", "-an"], "unix": ["ss", "-tunapo"]},
    "traceroute": {"windows": ["tracert", "-h", "10", "{target}"], "unix": ["traceroute", "-m", "10", "{target}"]},
    "nslookup": {"windows": ["nslookup", "{target}"], "unix": ["nslookup", "{target}"]},
    "ipconfig": {"windows": ["ipconfig", "/all"], "unix": ["ip", "addr", "show"]},
    "arp": {"windows": ["arp", "-a"], "unix": ["arp", "-n"]},
    "route": {"windows": ["route", "print"], "unix": ["ip", "route", "show"]},
    "who": {"windows": ["query", "session"], "unix": ["who"]},
}

DEFAULT_TARGET = "8.8.8.8"


def parse_from_ai_text(text: str) -> str | None:
    text = (text or "").lower()
    for name in COMMANDS:
        if name in text:
            return name
    return None


def execute(command_name: str, target: str | None = None) -> dict[str, Any]:
    command_name = (command_name or "").strip().lower()
    if command_name not in COMMANDS:
        return {
            "status": "blocked",
            "command": command_name,
            "cmd_string": "",
            "output": "Command is not in the whitelist.",
            "output_lines": [],
        }

    target = (target or DEFAULT_TARGET).strip() or DEFAULT_TARGET
    mapping = COMMANDS[command_name]["windows" if WINDOWS else "unix"]
    argv = [part.replace("{target}", target) for part in mapping]
    cmd_string = " ".join(shlex.quote(part) for part in argv)

    try:
        log("EXECUTOR", f"Running diagnostic command: {cmd_string}")
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=25,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        status = "ok" if completed.returncode == 0 else "warning"
    except FileNotFoundError:
        output = f"Required command is not installed: {argv[0]}"
        status = "missing"
    except subprocess.TimeoutExpired:
        output = "Command timed out after 25 seconds."
        status = "timeout"
    except Exception as exc:
        output = f"Executor error: {exc}"
        status = "error"

    log("EXECUTOR", f"{command_name} finished with status={status}")
    return {
        "status": status,
        "command": command_name,
        "cmd_string": cmd_string,
        "output": output,
        "output_lines": output.splitlines()[:40],
    }
