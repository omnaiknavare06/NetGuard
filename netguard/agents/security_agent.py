"""SecurityAgent — detects and diagnoses failed-login attacks and brute force."""
from __future__ import annotations
from typing import Any
from agents.base import BaseAgent, AgentResult


class SecurityAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("SecurityAgent")

    def _heuristic(self, alert: dict[str, Any]) -> AgentResult:
        failed = alert.get("failed_logins", 0)
        reason = alert.get("reason", "")

        if failed >= 20:
            sev = "Critical"
            cause = f"Ongoing brute-force attack: {failed} failed logins detected. Likely automated credential stuffing."
            action = "Immediately block the source IP. Enable account lockout after 5 attempts."
            resolved = False
        elif failed >= 10:
            sev = "High"
            cause = f"High volume of failed logins ({failed}). Possible brute-force or misconfigured client."
            action = "Enable rate-limiting per IP. Review auth logs for repeating source addresses."
            resolved = False
        else:
            sev = "Medium"
            cause = f"Moderate failed login count ({failed}). Could be user error or probing."
            action = "Monitor login attempts. Alert if count rises above 10 in the next cycle."
            resolved = True

        return AgentResult(
            agent_name=self.name,
            alert_key="failed_login",
            alert_reason=reason,
            severity=sev,
            root_cause=cause,
            immediate_action=action,
            preventive_measures=[
                "Implement exponential backoff on failed auth attempts.",
                "Deploy fail2ban or IP-level rate limiting at the edge.",
                "Add multi-factor authentication for all privileged accounts.",
                "Set up alerts for >5 failed logins from a single IP within 60 seconds.",
            ],
            confidence="Heuristic",
            resolved=resolved,
            escalation_needed=not resolved,
        )

    def _gemini_prompt(self, alert: dict[str, Any]) -> str:
        return f"""You are a network security analyst AI agent.
Alert: {alert.get('reason')}
Failed logins: {alert.get('failed_logins', 0)}
Active sessions: {alert.get('active', 0)}
Return JSON with keys: root_cause, severity, immediate_action, preventive_measures (list), resolved (bool), escalation_needed (bool).
Be specific and actionable. Severity must be: Low, Medium, High, or Critical."""
