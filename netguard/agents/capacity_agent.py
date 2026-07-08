"""CapacityAgent — handles session overload, queue pressure, and rejection storms."""
from __future__ import annotations
from typing import Any
from agents.base import BaseAgent, AgentResult


class CapacityAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("CapacityAgent")

    def _heuristic(self, alert: dict[str, Any]) -> AgentResult:
        active = alert.get("active", 0)
        max_cap = alert.get("max_capacity", 10)
        key = alert.get("key", "capacity_degrade")
        reason = alert.get("reason", "")
        load_pct = round((active / 15) * 100)

        if key == "capacity_critical" or active >= 14:
            sev = "Critical"
            cause = f"Server at {load_pct}% capacity ({active}/15 sessions). New connections are being REJECTED. Service is unavailable for new users."
            action = "Scale horizontally immediately. Enable request queuing. Review session TTL and evict idle sessions."
            resolved = False
        elif active > max_cap:
            sev = "High"
            cause = f"Server in DEGRADED mode at {load_pct}% ({active}/{max_cap + 5} sessions). New clients are being queued, causing latency increases."
            action = "Drain idle sessions. Prepare to redirect traffic to a backup instance."
            resolved = False
        else:
            sev = "Medium"
            cause = f"Session count approaching normal limit ({active}/{max_cap})."
            action = "Monitor for further growth. Pre-warm backup capacity."
            resolved = True

        return AgentResult(
            agent_name=self.name,
            alert_key=key,
            alert_reason=reason,
            severity=sev,
            root_cause=cause,
            immediate_action=action,
            preventive_measures=[
                "Implement session TTL to auto-evict idle connections.",
                "Configure connection pooling and reuse.",
                "Set up horizontal scaling triggers at 70% capacity.",
                "Add a load balancer to distribute sessions across multiple instances.",
            ],
            confidence="Heuristic",
            resolved=resolved,
            escalation_needed=not resolved,
        )

    def _gemini_prompt(self, alert: dict[str, Any]) -> str:
        return f"""You are a capacity planning AI agent.
Alert: {alert.get('reason')}
Active sessions: {alert.get('active', 0)} / 15 max
Mode: {alert.get('key', 'unknown')}
Return JSON: root_cause, severity (Low/Medium/High/Critical), immediate_action, preventive_measures (list), resolved (bool), escalation_needed (bool)."""
