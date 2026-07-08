from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from executor import DEFAULT_TARGET, execute
from logger import log

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"


def _call(api_key: str, prompt: str) -> str:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GEMINI_URL.format(api_key=api_key),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == 2:
                break
            time.sleep(2 ** attempt)
        except Exception as exc:
            last_error = exc
            break
    raise RuntimeError(f"Gemini request failed: {last_error}")


def _parse_json(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?", "", raw or "").replace("```", "").strip()
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return fallback


def _heuristic_command(alert: dict[str, Any], previous: list[dict[str, Any]]) -> dict[str, Any]:
    reason = alert["reason"].lower()
    used = {item["command"] for item in previous}
    ordered = [
        ("failed login", "netstat"),
        ("critical", "arp"),
        ("degraded", "ipconfig"),
        ("cpu", "who"),
        ("ram", "netstat"),
        ("request rate", "netstat"),
        ("bandwidth", "traceroute"),
        ("latency", "ping"),
    ]
    chosen = "netstat"
    for key, candidate in ordered:
        if key in reason and candidate not in used:
            chosen = candidate
            break
    if chosen in used:
        for candidate in ("netstat", "who", "arp", "ping", "route", "ipconfig", "nslookup", "traceroute"):
            if candidate not in used:
                chosen = candidate
                break
    return {
        "command": chosen,
        "target": DEFAULT_TARGET,
        "reason": "Local heuristic selected a safe diagnostic command.",
        "suspected_issue": alert["reason"],
        "risk_level": "Medium",
    }


def suggest_command(api_key: str | None, alert: dict[str, Any], iteration: int, previous_actions: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = _heuristic_command(alert, previous_actions)
    if not api_key:
        return fallback

    prompt = f"""
You are helping diagnose a network incident.
Return JSON only with keys: command, target, reason, suspected_issue, risk_level.
Allowed commands: ping, netstat, traceroute, nslookup, ipconfig, arp, route, who.
Current alert reason: {alert['reason']}
CPU: {alert['cpu_pct']} RAM: {alert['ram_pct']} RPM: {alert['rpm']} Sessions: {alert['active']}
Failed logins: {alert['failed_logins']} High latency clients: {alert.get('high_latency_clients', [])}
Iteration: {iteration + 1}
Previous actions: {json.dumps(previous_actions)}
Do not repeat a command already used unless absolutely necessary.
""".strip()

    try:
        log("AI", f"Gemini suggest_command request for incident reason: {alert['reason']}")
        raw = _call(api_key, prompt)
        result = _parse_json(raw, fallback)
        result["command"] = result.get("command") or fallback["command"]
        result["target"] = result.get("target") or DEFAULT_TARGET
        return result
    except Exception as exc:
        log("AI", f"Falling back to heuristic command selection: {exc}")
        return fallback


def _heuristic_analysis(alert: dict[str, Any], command_name: str, executor_result: dict[str, Any]) -> dict[str, Any]:
    reason = alert["reason"]
    resolved = command_name in {"netstat", "who"} or executor_result["status"] in {"missing", "timeout"}
    measures = [
        "Add rate limiting per client or IP.",
        "Queue heavy compute and bulk jobs.",
        "Review session rejection and backpressure thresholds.",
    ]
    if "failed login" in reason.lower():
        measures = [
            "Enable lockouts or fail2ban-style blocking.",
            "Add MFA for privileged access.",
            "Monitor suspicious source IPs on the edge firewall.",
        ]
    elif "bandwidth" in reason.lower() or "latency" in reason.lower():
        measures = [
            "Throttle large transfers during peak periods.",
            "Separate streaming traffic from critical control traffic.",
            "Add dashboards for per-client throughput trends.",
        ]
    return {
        "root_cause": reason,
        "explanation": f"Local analysis used the alert context plus '{command_name}' output to estimate likely pressure points.",
        "severity": "High" if any(word in reason.lower() for word in ("critical", "failed login", "bandwidth")) else "Medium",
        "resolved": resolved,
        "immediate_action": "Review the current sessions and reduce heavy traffic or block suspicious sources.",
        "preventive_measures": measures,
        "escalation_needed": not resolved,
    }


def analyze_output(
    api_key: str | None,
    cmd_name: str,
    cmd_output: str,
    alert: dict[str, Any],
    iteration: int,
) -> dict[str, Any]:
    fallback = _heuristic_analysis(alert, cmd_name, {"status": "ok", "output": cmd_output})
    if not api_key:
        return fallback

    prompt = f"""
You are diagnosing a network incident.
Return JSON only with keys: root_cause, explanation, severity, resolved, immediate_action, preventive_measures, escalation_needed.
Original alert: {json.dumps(alert)}
Iteration: {iteration + 1}
Command run: {cmd_name}
Command output:
{cmd_output[:1800]}
""".strip()

    try:
        log("AI", f"Gemini analyze_output request for command={cmd_name}")
        raw = _call(api_key, prompt)
        return _parse_json(raw, fallback)
    except Exception as exc:
        log("AI", f"Falling back to heuristic diagnosis: {exc}")
        return fallback


def run_pipeline(api_key: str | None, alert: dict[str, Any]) -> dict[str, Any]:
    iterations: list[dict[str, Any]] = []
    previous_actions: list[dict[str, Any]] = []
    final_diagnosis: dict[str, Any] | None = None

    for iteration in range(3):
        log("PIPELINE", f"Incident iteration {iteration + 1} started")
        suggestion = suggest_command(api_key, alert, iteration, previous_actions)
        command = suggestion.get("command", "netstat")
        target = suggestion.get("target", DEFAULT_TARGET)
        executor_result = execute(command, target)
        diagnosis = analyze_output(api_key, command, executor_result["output"], alert, iteration)
        entry = {
            "iteration": iteration + 1,
            "command": command,
            "target": target,
            "cmd_string": executor_result["cmd_string"],
            "cmd_output": executor_result["output"][:4000],
            "suggestion": suggestion,
            "diagnosis": diagnosis,
        }
        iterations.append(entry)
        previous_actions.append({"command": command, "severity": diagnosis.get("severity"), "resolved": diagnosis.get("resolved")})
        final_diagnosis = diagnosis
        if diagnosis.get("resolved"):
            break

    incident = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "alert": alert,
        "iterations": iterations,
        "final_diagnosis": final_diagnosis or {},
        "resolved": bool(final_diagnosis and final_diagnosis.get("resolved")),
        "total_iterations": len(iterations),
    }
    return incident
