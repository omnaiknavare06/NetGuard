"""LatencyAgent — diagnoses high-latency client connections and slow response patterns."""
from __future__ import annotations
from typing import Any
from agents.base import BaseAgent, AgentResult


class LatencyAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("LatencyAgent")

    def _heuristic(self, alert: dict[str, Any]) -> AgentResult:
        clients = alert.get("high_latency_clients", [])
        cpu = alert.get("cpu_pct", 0)
        ram = alert.get("ram_pct", 0)
        active = alert.get("active", 0)
        reason = alert.get("reason", "")
        count = len(clients)

        if count >= 5:
            sev = "High"
            cause = f"{count} clients are experiencing latency >1500ms. System-wide slowdown — likely CPU ({cpu}%) or RAM ({ram}%) pressure causing queuing delays."
            action = "Drain heavy tasks. Reduce concurrent compute and bulk sessions. Check for GC pauses or lock contention."
            resolved = False
        elif count >= 2:
            sev = "Medium"
            cause = f"{count} clients ({', '.join(clients[:3])}) experiencing high latency. Could be CPU ({cpu}%) contention or task queuing."
            action = "Identify what tasks these clients are running. Throttle heavy tasks if load is high."
            resolved = False
        else:
            sev = "Low"
            cause = f"1 client ({clients[0] if clients else '?'}) experiencing high latency. Likely isolated — heavy task or degraded network."
            action = "Monitor the specific client. If persistent, ask client to retry with lighter tasks."
            resolved = True

        return AgentResult(
            agent_name=self.name,
            alert_key="latency_high",
            alert_reason=reason,
            severity=sev,
            root_cause=cause,
            immediate_action=action,
            preventive_measures=[
                "Set server-side timeout limits per task type.",
                "Add latency-based session prioritization (deprioritize high-latency clients).",
                "Profile task execution times and set SLO budgets.",
                "Implement heartbeat timeouts to detect and evict stale sessions.",
            ],
            confidence="Heuristic",
            resolved=resolved,
            escalation_needed=not resolved,
        )

    def _gemini_prompt(self, alert: dict[str, Any]) -> str:
        return f"""You are a network latency AI agent.
Alert: {alert.get('reason')}
High-latency clients: {alert.get('high_latency_clients', [])}
CPU: {alert.get('cpu_pct')}%  RAM: {alert.get('ram_pct')}%  Active sessions: {alert.get('active')}
Return JSON: root_cause, severity (Low/Medium/High/Critical), immediate_action, preventive_measures (list), resolved (bool), escalation_needed (bool)."""
