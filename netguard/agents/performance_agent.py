"""PerformanceAgent — diagnoses CPU spikes, RAM pressure, bandwidth storms, RPM surges."""
from __future__ import annotations
from typing import Any
from agents.base import BaseAgent, AgentResult


class PerformanceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("PerformanceAgent")

    def _heuristic(self, alert: dict[str, Any]) -> AgentResult:
        cpu = alert.get("cpu_pct", 0)
        ram = alert.get("ram_pct", 0)
        rpm = alert.get("rpm", 0)
        bw = alert.get("bandwidth_bytes_s", 0)
        key = alert.get("key", "cpu_high")
        reason = alert.get("reason", "")

        # Determine dominant issue
        if key == "cpu_high" or cpu >= 80:
            sev = "High" if cpu >= 90 else "Medium"
            cause = f"CPU at {cpu}%. Heavy compute or bulk processing tasks are saturating the processor."
            action = "Throttle compute-intensive tasks. Queue bulk_process and compute jobs. Check for runaway threads."
            measures = [
                "Implement task queuing for heavy compute jobs.",
                "Add CPU usage limits per client session.",
                "Offload compute tasks to a background worker process.",
                "Profile the most CPU-intensive tasks and optimize them.",
            ]
        elif key == "ram_high" or ram >= 85:
            sev = "High" if ram >= 92 else "Medium"
            cause = f"RAM at {ram}%. File uploads or high-session counts are consuming memory."
            action = "Evict cached objects. Limit concurrent file_upload and stream tasks per client."
            measures = [
                "Add memory limits per session/task type.",
                "Implement streaming for large file operations instead of buffering.",
                "Configure garbage collection tuning.",
                "Set up swap space as an emergency buffer.",
            ]
        elif key == "bandwidth_high" or bw >= 5_000_000:
            kb_s = round(bw / 1024, 1)
            sev = "High"
            cause = f"Bandwidth at {kb_s} KB/s. Large file transfers or streaming sessions are saturating the network."
            action = "Rate-limit per-client bandwidth. Prioritize control traffic over bulk data."
            measures = [
                "Add per-client bandwidth throttling.",
                "Separate bulk transfer traffic to a dedicated network interface.",
                "Cache frequently downloaded files at the edge.",
                "Compress data payloads before transmission.",
            ]
        elif key == "rpm_high" or rpm >= 80:
            sev = "Medium"
            cause = f"Request rate at {rpm} RPM. Possible bot traffic or rapid client cycling."
            action = "Enable request rate limiting per client IP. Check for clients in retry loops."
            measures = [
                "Implement per-client RPM caps.",
                "Add exponential backoff in client error handling.",
                "Use a CDN or reverse proxy to absorb traffic spikes.",
            ]
        else:
            sev = "Low"
            cause = "Minor performance anomaly detected."
            action = "Monitor for escalation."
            measures = ["Continue monitoring."]

        resolved = sev == "Low"
        return AgentResult(
            agent_name=self.name,
            alert_key=key,
            alert_reason=reason,
            severity=sev,
            root_cause=cause,
            immediate_action=action,
            preventive_measures=measures,
            confidence="Heuristic",
            resolved=resolved,
            escalation_needed=not resolved,
        )

    def _gemini_prompt(self, alert: dict[str, Any]) -> str:
        return f"""You are a server performance AI agent.
Alert: {alert.get('reason')}
CPU: {alert.get('cpu_pct')}%  RAM: {alert.get('ram_pct')}%
RPM: {alert.get('rpm')}  Bandwidth: {alert.get('bandwidth_bytes_s', 0)} bytes/s
Return JSON: root_cause, severity (Low/Medium/High/Critical), immediate_action, preventive_measures (list), resolved (bool), escalation_needed (bool)."""
