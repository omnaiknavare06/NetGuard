"""monitor.py — Background surveillance daemon. Polls state, raises alerts, calls Orchestrator."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from agents.orchestrator import Orchestrator
from logger import log
from state_manager import StateManager

POLL_INTERVAL = 2
ALERT_COOLDOWN = 5  # short cooldown so demo triggers feel responsive


class MonitorEngine:
    def __init__(self, state: StateManager, broadcaster: Callable[[str, Any], None]) -> None:
        self.state = state
        self._broadcast = broadcaster
        self._orchestrator = Orchestrator(state, broadcaster)
        self._alert_cooldowns: dict[str, float] = {}
        self._thread: threading.Thread | None = None

    def start(self, api_key: str | None) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._api_key = api_key
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="netguard-monitor"
        )
        self._thread.start()
        log("MONITOR", f"Monitoring engine started (poll every {POLL_INTERVAL}s).")

    def get_agent_log(self) -> list[dict[str, Any]]:
        return self._orchestrator.get_agent_log()

    def _loop(self) -> None:
        while True:
            try:
                self._sweep()
            except Exception as exc:
                log("MONITOR", f"Sweep error: {exc}")
            time.sleep(POLL_INTERVAL)

    def _sweep(self) -> None:
        self.state._natural_decay()
        snap = self.state.snapshot()
        alerts = self._check_conditions(snap)
        if not alerts:
            return

        for alert in alerts:
            self.state.add_alert({"key": alert["key"], "reason": alert["reason"], "timestamp": snap["timestamp"]})
            log("MONITOR", alert["reason"])

        self._broadcast("alerts", [{"key": a["key"], "reason": a["reason"], "timestamp": snap["timestamp"]} for a in alerts])
        context = self._build_context(snap, alerts)
        self._orchestrator.dispatch(context, self._api_key)

    def _check_conditions(self, snap: dict[str, Any]) -> list[dict[str, Any]]:
        now = time.time()
        m = snap["metrics"]
        c = snap["capacity"]
        alerts = []

        def allow(key: str) -> bool:
            prev = self._alert_cooldowns.get(key, 0.0)
            if now - prev < ALERT_COOLDOWN:
                return False
            self._alert_cooldowns[key] = now
            return True

        if m["failed_logins"] >= 5 and allow("failed_login"):
            alerts.append({"key": "failed_login", "reason": f"High failed login count ({m['failed_logins']} attempts)"})
        if c["active_sessions"] > max(6, c["max_normal"] - 2) and allow("capacity_degrade"):
            alerts.append({"key": "capacity_degrade", "reason": f"Server DEGRADED ({c['active_sessions']}/14 sessions)"})
        if c["active_sessions"] >= max(10, c["max_reject"] - 2) and allow("capacity_critical"):
            alerts.append({"key": "capacity_critical", "reason": "Server CRITICAL — rejecting new connections"})
        if m["cpu_pct"] >= 65 and allow("cpu_high"):
            alerts.append({"key": "cpu_high", "reason": f"CPU critical ({m['cpu_pct']}%)"})
        if m["ram_pct"] >= 70 and allow("ram_high"):
            alerts.append({"key": "ram_high", "reason": f"RAM critical ({m['ram_pct']}%)"})
        if m["rpm"] >= 30 and allow("rpm_high"):
            alerts.append({"key": "rpm_high", "reason": f"Request rate spike ({m['rpm']} RPM)"})
        if m["bandwidth_bytes_s"] >= 1_500_000 and allow("bandwidth_high"):
            alerts.append({"key": "bandwidth_high", "reason": f"Bandwidth spike ({m['bandwidth_bytes_s']//1024} KB/s)"})
        if m["high_latency_clients"] and allow("latency_high"):
            clients = ", ".join(m["high_latency_clients"][:3])
            alerts.append({"key": "latency_high", "reason": f"High latency clients: {clients}"})

        return alerts

    def _build_context(self, snap: dict[str, Any], alerts: list[dict[str, Any]]) -> dict[str, Any]:
        m = snap["metrics"]
        c = snap["capacity"]
        return {
            "reason": " | ".join(a["reason"] for a in alerts),
            "conditions": [a["key"] for a in alerts],
            "active": c["active_sessions"],
            "max_capacity": c["max_normal"],
            "cpu_pct": m["cpu_pct"],
            "ram_pct": m["ram_pct"],
            "failed_logins": m["failed_logins"],
            "rpm": m["rpm"],
            "bandwidth_bytes_s": m["bandwidth_bytes_s"],
            "high_latency_clients": m["high_latency_clients"],
            "suspect_ips": self._suspect_ips(snap),
            "timestamp": snap["timestamp"],
        }

    @staticmethod
    def _suspect_ips(snap: dict[str, Any]) -> list[str]:
        ips: list[str] = []
        for session in snap.get("sessions", []):
            if session.get("error_count", 0) >= 2:
                ip = str(session.get("ip", "")).strip()
                if ip and ip not in ips:
                    ips.append(ip)
        return ips[:5]
