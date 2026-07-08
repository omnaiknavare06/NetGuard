"""orchestrator.py — Main AI brain: routes alerts → agents → executes actions → reports.

Flow:
  1. Monitor detects alert condition
  2. Orchestrator classifies which agents to activate
  3. Each agent runs heuristic + optional Gemini call
  4. Orchestrator executes concrete actions based on diagnosis  ← NEW
  5. Builds IncidentReport with actions taken
  6. Broadcasts to dashboard
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from agents.security_agent import SecurityAgent
from agents.capacity_agent import CapacityAgent
from agents.performance_agent import PerformanceAgent
from agents.latency_agent import LatencyAgent
from agents.base import AgentResult
from executor import execute as execute_command
from logger import log, save_incident


# ── Routing map: alert key → agent class ──────────────────────────────────────
_AGENT_REGISTRY: dict[str, type] = {
    "failed_login":       SecurityAgent,
    "capacity_degrade":   CapacityAgent,
    "capacity_critical":  CapacityAgent,
    "cpu_high":           PerformanceAgent,
    "ram_high":           PerformanceAgent,
    "rpm_high":           PerformanceAgent,
    "bandwidth_high":     PerformanceAgent,
    "latency_high":       LatencyAgent,
}

# ── What action to execute for each alert key (plain-English descriptions) ────
_ACTION_MAP: dict[str, list[dict[str, str]]] = {
    "failed_login": [
        {"type": "block_ip",           "desc": "Blocked suspicious source IPs",           "detail_key": "ip"},
        {"type": "reset_failed_logins","desc": "Reset failed-login counter to 0",          "detail": ""},
    ],
    "capacity_degrade": [
        {"type": "drop_simulated_sessions", "desc": "Dropped low-priority simulated sessions", "detail": ""},
        {"type": "enable_queue_mode",       "desc": "Enabled strict queue mode for new connections", "detail": ""},
    ],
    "capacity_critical": [
        {"type": "drop_simulated_sessions", "desc": "Emergency: terminated all simulated sessions", "detail": ""},
        {"type": "enable_queue_mode",       "desc": "Server switched to REJECT mode — protecting real users", "detail": ""},
    ],
    "cpu_high": [
        {"type": "throttle_cpu",   "desc": "CPU throttled — heavy tasks paused", "detail": ""},
        {"type": "throttle_clients","desc": "Degraded sessions put in low-priority mode",  "detail": ""},
    ],
    "ram_high": [
        {"type": "free_memory",    "desc": "Memory freed — garbage collected inactive caches", "detail": ""},
        {"type": "throttle_clients","desc": "High-memory clients rate-limited",               "detail": ""},
    ],
    "rpm_high": [
        {"type": "throttle_clients","desc": "Rate limiter activated on burst-traffic clients", "detail": ""},
    ],
    "bandwidth_high": [
        {"type": "throttle_clients","desc": "Bandwidth throttle enabled for download sessions", "detail": ""},
    ],
    "latency_high": [
        {"type": "throttle_clients","desc": "Slow-response clients deprioritized",             "detail": ""},
        {"type": "alert_cleared",   "desc": "Latency watchdog reset — monitoring response times","detail": ""},
    ],
}

_COMMAND_MAP: dict[str, list[str]] = {
    "failed_login": ["netstat", "arp"],
    "capacity_degrade": ["netstat", "route"],
    "capacity_critical": ["netstat", "route", "who"],
    "cpu_high": ["netstat", "ipconfig"],
    "ram_high": ["ipconfig", "netstat"],
    "rpm_high": ["netstat", "arp"],
    "bandwidth_high": ["netstat", "traceroute"],
    "latency_high": ["ping", "traceroute"],
}


class Orchestrator:
    """Main multi-agent coordinator. One instance per server."""

    def __init__(self, state: Any, broadcaster: Callable[[str, Any], None]) -> None:
        self.state = state
        self._broadcast = broadcaster
        self._agents: dict[str, Any] = {}
        self._agent_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    # ── Public ───────────────────────────────────────────────────────────────

    def dispatch(self, alert_snapshot: dict[str, Any], api_key: str | None) -> None:
        """Entry point called by the monitor. Runs in a background thread."""
        threading.Thread(
            target=self._run_pipeline,
            args=(alert_snapshot, api_key),
            daemon=True,
            name="netguard-orchestrator",
        ).start()

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def _run_pipeline(self, alert: dict[str, Any], api_key: str | None) -> None:
        conditions: list[str] = alert.get("conditions", [])
        if not conditions:
            return

        log("ORCHESTR", f"[START] Dispatching for conditions: {conditions}")
        results: list[AgentResult] = []
        executed: list[dict[str, Any]] = []
        command_runs: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = [{
            "step": "alert_detected",
            "status": "ok",
            "detail": f"Monitor raised conditions: {', '.join(conditions)}",
            "timestamp": time.strftime("%H:%M:%S"),
        }]

        for key in conditions:
            agent_class = _AGENT_REGISTRY.get(key)
            if not agent_class:
                continue

            agent_name = agent_class.__name__
            if agent_name not in self._agents:
                self._agents[agent_name] = agent_class()
            agent = self._agents[agent_name]

            sub_alert = {**alert, "key": key}

            log("ORCHESTR", f"[AGENT] Activating {agent_name} for '{key}'")
            timeline.append({
                "step": "agent_started",
                "status": "running",
                "detail": f"{agent_name} started for {key}",
                "timestamp": time.strftime("%H:%M:%S"),
            })
            self._add_agent_log(agent_name, key, "running")
            try:
                result = agent.analyse(sub_alert, api_key)
                results.append(result)
                self._add_agent_log(agent_name, key, "done", result.severity)
                log("ORCHESTR", f"[DONE]  {agent_name}: {result.severity} | {result.confidence}")
                timeline.append({
                    "step": "agent_result",
                    "status": "ok",
                    "detail": f"{agent_name} -> {result.severity} ({result.confidence})",
                    "timestamp": time.strftime("%H:%M:%S"),
                })

                # ── Execute AI-directed actions ──────────────────────
                actions = self._execute_actions_for(key, agent_name, alert)
                executed.extend(actions)
                timeline.append({
                    "step": "actions_executed",
                    "status": "ok",
                    "detail": f"{len(actions)} action(s) executed for {key}",
                    "timestamp": time.strftime("%H:%M:%S"),
                })

                # ── Execute whitelisted diagnostics automatically ────
                cmd = self._execute_commands_for(key, agent_name, alert)
                command_runs.extend(cmd)
                timeline.append({
                    "step": "diagnostics_executed",
                    "status": "ok",
                    "detail": f"{len(cmd)} diagnostic command(s) executed for {key}",
                    "timestamp": time.strftime("%H:%M:%S"),
                })

            except Exception as exc:
                log("ORCHESTR", f"[FAIL]  {agent_name} error: {exc}")
                self._add_agent_log(agent_name, key, "error")
                timeline.append({
                    "step": "agent_error",
                    "status": "error",
                    "detail": f"{agent_name} failed for {key}: {exc}",
                    "timestamp": time.strftime("%H:%M:%S"),
                })

        if not results:
            return

        # Build and save incident report
        incident = self._build_incident(alert, results, executed, command_runs, timeline)
        incident["incident_id"] = self.state.incident_count + 1

        filename = save_incident(incident)
        incident["report_file"] = filename
        self.state.set_last_diagnosis(incident)

        log(
            "ORCHESTR",
            f"[SAVED] Incident #{incident['incident_id']} — {len(executed)} action(s), {len(command_runs)} command(s)",
        )

        # Broadcast to dashboard
        self._broadcast("incident", incident)
        self._broadcast("agents", self.get_agent_log())
        self._broadcast("state", self.state.snapshot())

    def _execute_actions_for(self, key: str, agent_name: str, alert: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute concrete remediation actions for the given alert key."""
        action_defs = _ACTION_MAP.get(key, [])
        executed = []
        for ad in action_defs:
            # Resolve dynamic detail (e.g. client IP from alert)
            detail = ad.get("detail", "")
            if ad.get("detail_key") == "ip":
                suspects = [str(ip) for ip in alert.get("suspect_ips", []) if ip]
                detail = ",".join(suspects)

            # Skip unsafe/no-op dynamic actions.
            if ad["type"] == "block_ip" and not detail:
                log("ORCHESTR", "[ACT]   Skipped IP block (no blockable suspect IP found)")
                continue

            action = self.state.execute_action(
                action_type=ad["type"],
                description=ad["desc"],
                detail=detail,
                agent=agent_name,
            )
            log("ORCHESTR", f"[ACT]   {ad['desc']} -> {action.get('result','ok')}")
            executed.append(action)
        return executed

    def _execute_commands_for(self, key: str, agent_name: str, alert: dict[str, Any]) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        commands = _COMMAND_MAP.get(key, [])
        suspects = [str(ip) for ip in alert.get("suspect_ips", []) if ip]
        target = suspects[0] if suspects else "8.8.8.8"

        for command_name in commands:
            result = execute_command(command_name, target=target)
            run = {
                "agent": agent_name,
                "alert_key": key,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target": target,
                **result,
                "output_preview": "\n".join(result.get("output_lines", [])[:6]),
            }
            runs.append(run)
            log("ORCHESTR", f"[CMD]   {command_name} -> {result.get('status')}")

        return runs

    def _build_incident(
        self,
        alert: dict[str, Any],
        results: list[AgentResult],
        executed: list[dict[str, Any]],
        command_runs: list[dict[str, Any]],
        timeline: list[dict[str, Any]],
    ) -> dict[str, Any]:
        severity_order = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        primary = max(results, key=lambda r: severity_order.get(r.severity, 0))
        all_measures: list[str] = []
        seen: set[str] = set()
        for r in results:
            for m in r.preventive_measures:
                if m not in seen:
                    all_measures.append(m)
                    seen.add(m)

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "alert": alert,
            "agents_used": [r.agent_name for r in results],
            "agent_results": [r.to_dict() for r in results],
            "executed_actions": executed,
            "command_runs": command_runs,
            "timeline": timeline,
            "ai_summary": {
                "gemini_used": sum(1 for r in results if "Gemini" in r.confidence),
                "heuristic_only": sum(1 for r in results if "Gemini" not in r.confidence),
            },
            "final_diagnosis": {
                "primary_agent": primary.agent_name,
                "root_cause": primary.root_cause,
                "severity": primary.severity,
                "immediate_action": primary.immediate_action,
                "preventive_measures": all_measures,
                "confidence": primary.confidence,
                "resolved": all(r.resolved for r in results),
                "escalation_needed": any(r.escalation_needed for r in results),
            },
            "resolved": all(r.resolved for r in results),
            "total_agents": len(results),
            "total_actions": len(executed),
            "total_commands": len(command_runs),
        }

    # ── Agent Activity Log ────────────────────────────────────────────────────

    def _add_agent_log(self, agent: str, key: str, status: str, severity: str = "") -> None:
        entry = {
            "agent": agent,
            "alert_key": key,
            "status": status,
            "severity": severity,
            "ts": time.strftime("%H:%M:%S"),
        }
        with self._lock:
            self._agent_log.insert(0, entry)
            if len(self._agent_log) > 50:
                self._agent_log.pop()

    def get_agent_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._agent_log)
