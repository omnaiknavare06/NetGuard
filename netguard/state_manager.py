from __future__ import annotations

import time
from collections import deque
from datetime import datetime
import ipaddress
from threading import RLock
from typing import Any


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class StateManager:
    MAX_NORMAL = 10
    MAX_REJECT = 15
    MAX_QUEUE = 50
    MAX_ALERTS = 20
    ALERT_TTL_SECONDS = 45

    def __init__(self) -> None:
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            # Restore capacity thresholds in case mitigation actions changed them.
            self.MAX_NORMAL = 10
            self.MAX_REJECT = 15
            self.sessions: dict[str, dict[str, Any]] = {}
            self.request_queue: deque[dict[str, Any]] = deque(maxlen=self.MAX_QUEUE)
            self.failed_logins = 0
            self.cpu_sim_pct = 15.0
            self.ram_sim_pct = 25.0
            self.bw_bytes_s = 0
            self._bandwidth_samples: deque[tuple[float, int]] = deque(maxlen=500)
            self.active_alerts: deque[dict[str, Any]] = deque(maxlen=self.MAX_ALERTS)
            self.last_diagnosis: dict[str, Any] | None = None
            self.incident_count = 0
            self.rejected_requests = 0
            self.queued_requests = 0
            self._request_timestamps: deque[float] = deque(maxlen=5000)
            # --- NEW: action execution tracking ---
            self.executed_actions: deque[dict[str, Any]] = deque(maxlen=50)
            self.blacklisted_ips: set[str] = set()
            self.throttled_clients: set[str] = set()
            self.cpu_throttle_active = False
            self.memory_freed_mb = 0

    # ───────────────────────────── ACTION EXECUTION ───────────────────────────

    def execute_action(self, action_type: str, description: str, detail: str = "", agent: str = "") -> dict[str, Any]:
        """Record and 'execute' an AI-directed action. Returns the action record."""
        with self._lock:
            action: dict[str, Any] = {
                "action_type": action_type,
                "description": description,
                "detail": detail,
                "agent": agent,
                "timestamp": _now_text(),
                "status": "executed",
            }

            # Actually enforce the action in state
            if action_type == "block_ip" and detail:
                blocked = 0
                terminated = 0
                for ip in [x.strip() for x in detail.split(",") if x.strip()]:
                    if not self._is_blockable_ip(ip):
                        continue
                    self.blacklisted_ips.add(ip)
                    blocked += 1
                    # Remove any sessions from that IP
                    to_remove = [cid for cid, s in self.sessions.items() if s["ip"] == ip]
                    terminated += len(to_remove)
                    for cid in to_remove:
                        self.sessions.pop(cid, None)
                action["result"] = f"Blocked {blocked} IP(s). Sessions terminated: {terminated}."

            elif action_type == "reset_failed_logins":
                self.failed_logins = 0
                self._drop_alerts_by_key("failed_login")
                action["result"] = "Failed login counter reset to 0."

            elif action_type == "throttle_cpu":
                self.cpu_throttle_active = True
                self.cpu_sim_pct = max(30.0, self.cpu_sim_pct - 25.0)
                action["result"] = f"CPU throttled. Load reduced to {self.cpu_sim_pct:.0f}%."

            elif action_type == "free_memory":
                freed = min(self.ram_sim_pct - 20.0, 30.0)
                self.ram_sim_pct = max(20.0, self.ram_sim_pct - freed)
                self.memory_freed_mb = int(freed * 20)
                action["result"] = f"Freed ~{self.memory_freed_mb} MB. RAM now at {self.ram_sim_pct:.0f}%."

            elif action_type == "drop_simulated_sessions":
                sims = [cid for cid, s in self.sessions.items() if s.get("simulated")]
                for cid in sims[:8]:
                    self.sessions.pop(cid, None)
                action["result"] = f"Dropped {min(len(sims),8)} simulated sessions."

            elif action_type == "enable_queue_mode":
                # Lower the normal threshold so queuing kicks in earlier
                self.MAX_NORMAL = max(5, self.MAX_NORMAL - 2)
                action["result"] = "Queue mode enabled. New sessions limited to high-priority only."

            elif action_type == "throttle_clients":
                # Mark all degraded sessions as throttled
                count = 0
                for cid, s in self.sessions.items():
                    if s.get("degraded") and cid not in self.throttled_clients:
                        self.throttled_clients.add(cid)
                        count += 1
                action["result"] = f"Throttled {count} degraded client sessions."

            elif action_type == "alert_cleared":
                action["result"] = "Alert condition resolved. System returning to normal."
                self.cpu_throttle_active = False

            else:
                action["result"] = "Action logged."

            self.executed_actions.appendleft(action)
            return action

    def update_capacity_limits(self, max_normal: int | None = None, max_reject: int | None = None) -> dict[str, int]:
        with self._lock:
            if max_normal is not None:
                self.MAX_NORMAL = max(3, min(int(max_normal), 100))
            if max_reject is not None:
                self.MAX_REJECT = max(self.MAX_NORMAL + 1, min(int(max_reject), 150))
            # Keep capacity ordering valid if only one side changed.
            if self.MAX_REJECT <= self.MAX_NORMAL:
                self.MAX_REJECT = self.MAX_NORMAL + 1
            return {"max_normal": self.MAX_NORMAL, "max_reject": self.MAX_REJECT}

    # ─────────────────────────── EXISTING METHODS ────────────────────────────

    def has_session(self, client_id: str) -> bool:
        with self._lock:
            return client_id in self.sessions

    def try_join(self, client_id: str, ip: str) -> dict[str, Any]:
        with self._lock:
            # Block blacklisted IPs
            if ip in self.blacklisted_ips:
                self.rejected_requests += 1
                return {"status": "rejected", "message": "IP address blocked by security policy."}

            now = time.time()
            if client_id in self.sessions:
                self.sessions[client_id]["last_seen"] = now
                return {"status": "ok", "message": "Client already connected."}

            active = len(self.sessions)
            if active >= self.MAX_REJECT:
                self.rejected_requests += 1
                return {"status": "rejected", "message": "Server full. Try later."}

            degraded = active >= self.MAX_NORMAL
            if degraded:
                self.queued_requests += 1
                self.request_queue.append({"client_id": client_id, "ip": ip, "at": _now_text()})

            self.sessions[client_id] = {
                "ip": ip,
                "joined_at": _now_text(),
                "degraded": degraded,
                "current_task": None,
                "task_count": 0,
                "error_count": 0,
                "latency_history": deque(maxlen=10),
                "last_seen": now,
                "last_result": "connected",
                "simulated": client_id.startswith("sim_"),
            }
            return {
                "status": "queued" if degraded else "ok",
                "message": "Connected in degraded mode." if degraded else "Connected.",
            }

    def leave(self, client_id: str) -> dict[str, Any]:
        with self._lock:
            if client_id not in self.sessions:
                return {"status": "missing", "message": "Client not connected."}
            self.sessions.pop(client_id, None)
            return {"status": "ok", "message": "Disconnected."}

    def set_current_task(self, client_id: str, task_name: str | None) -> None:
        with self._lock:
            session = self.sessions.get(client_id)
            if not session:
                return
            session["current_task"] = task_name
            session["last_seen"] = time.time()

    def record_request(self, bytes_in: int) -> None:
        now = time.time()
        with self._lock:
            self._request_timestamps.append(now)
            self._bandwidth_samples.append((now, max(0, int(bytes_in))))
            self._trim_samples(now)

    def update_resources(self, cpu_delta: float = 0.0, ram_delta: float = 0.0) -> None:
        with self._lock:
            self.cpu_sim_pct = max(0.0, min(100.0, self.cpu_sim_pct + cpu_delta))
            self.ram_sim_pct = max(0.0, min(100.0, self.ram_sim_pct + ram_delta))

    def add_failed_logins(self, count: int = 1) -> None:
        with self._lock:
            self.failed_logins += max(0, int(count))

    def record_task(self, client_id: str, task_name: str, latency_ms: float, *, success: bool, result_summary: str) -> None:
        with self._lock:
            session = self.sessions.get(client_id)
            if not session:
                return
            session["task_count"] += 1
            session["last_seen"] = time.time()
            session["current_task"] = None
            session["latency_history"].append(round(latency_ms, 1))
            session["last_result"] = result_summary
            if not success:
                session["error_count"] += 1

    def add_alert(self, alert: dict[str, Any]) -> None:
        with self._lock:
            if "at" not in alert:
                alert["at"] = time.time()
            self.active_alerts.appendleft(alert)

    def set_last_diagnosis(self, incident: dict[str, Any]) -> None:
        with self._lock:
            self.last_diagnosis = incident
            self.incident_count += 1

    def add_simulated_sessions(self, count: int) -> list[str]:
        added: list[str] = []
        for _ in range(max(0, int(count))):
            client_id = f"sim_{int(time.time() * 1000)}_{len(added)}"
            result = self.try_join(client_id, "127.0.0.1")
            if result["status"] == "rejected":
                break
            added.append(client_id)
        return added

    def inject_latency_spike(self, count: int = 3, latency_ms: float = 1400.0) -> list[str]:
        marked: list[str] = []
        with self._lock:
            for client_id, session in self.sessions.items():
                if len(marked) >= max(1, int(count)):
                    break
                # Push multiple samples so avg latency clearly crosses threshold.
                for _ in range(3):
                    session["latency_history"].append(round(float(latency_ms), 1))
                session["last_seen"] = time.time()
                marked.append(client_id)
        return marked

    def _trim_samples(self, now: float | None = None) -> None:
        now = now or time.time()
        while self._request_timestamps and now - self._request_timestamps[0] > 60:
            self._request_timestamps.popleft()
        while self._bandwidth_samples and now - self._bandwidth_samples[0][0] > 1:
            self._bandwidth_samples.popleft()
        self.bw_bytes_s = sum(size for _, size in self._bandwidth_samples)

    def _natural_decay(self) -> None:
        with self._lock:
            active = len(self.sessions)
            base_cpu = min(55.0, 8.0 + active * 1.8)
            base_ram = min(70.0, 18.0 + active * 2.4)
            # Respect throttle
            if self.cpu_throttle_active:
                base_cpu = min(base_cpu, 35.0)
            self.cpu_sim_pct = max(base_cpu, round(self.cpu_sim_pct - 6.5, 1))
            self.ram_sim_pct = max(base_ram, round(self.ram_sim_pct - 4.5, 1))
            # Slowly reduce login pressure so alerts can clear naturally.
            if self.failed_logins > 0:
                self.failed_logins = max(0, self.failed_logins - 1)
            self._prune_stale_sessions()
            self._prune_old_alerts()
            self._trim_samples()

    def _drop_alerts_by_key(self, key: str) -> None:
        keep = [a for a in self.active_alerts if a.get("key") != key]
        self.active_alerts.clear()
        self.active_alerts.extend(keep)

    def _prune_old_alerts(self) -> None:
        now = time.time()
        keep: list[dict[str, Any]] = []
        for alert in self.active_alerts:
            ts = alert.get("at")
            if isinstance(ts, (int, float)) and (now - ts) > self.ALERT_TTL_SECONDS:
                continue
            keep.append(alert)
        self.active_alerts.clear()
        self.active_alerts.extend(keep)

    def _prune_stale_sessions(self) -> None:
        now = time.time()
        stale: list[str] = []
        for client_id, session in self.sessions.items():
            idle = now - float(session.get("last_seen", now))
            # Auto-clean demo sessions faster than real clients.
            if session.get("simulated") and idle > 30:
                stale.append(client_id)
            elif idle > 180:
                stale.append(client_id)
        for client_id in stale:
            self.sessions.pop(client_id, None)

    @staticmethod
    def _is_blockable_ip(ip: str) -> bool:
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            return False
        # Do not block localhost/private/link-local in simulator mode.
        if parsed.is_loopback or parsed.is_private or parsed.is_link_local:
            return False
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._trim_samples()
            sessions: list[dict[str, Any]] = []
            high_latency_clients: list[str] = []
            for client_id, session in sorted(self.sessions.items()):
                history = list(session["latency_history"])
                avg_latency = round(sum(history) / len(history), 1) if history else 0.0
                if avg_latency > 700:
                    high_latency_clients.append(client_id)
                sessions.append({
                    "client_id": client_id,
                    "ip": session["ip"],
                    "joined_at": session["joined_at"],
                    "degraded": session["degraded"],
                    "current_task": session["current_task"],
                    "task_count": session["task_count"],
                    "error_count": session["error_count"],
                    "latency_history": history,
                    "avg_latency_ms": avg_latency,
                    "last_seen": round(session["last_seen"], 2),
                    "last_result": session["last_result"],
                    "simulated": session["simulated"],
                    "throttled": client_id in self.throttled_clients,
                })

            active = len(self.sessions)
            mode = "normal"
            if active >= self.MAX_REJECT:
                mode = "reject"
            elif active > self.MAX_NORMAL:
                mode = "degraded"

            return {
                "timestamp": _now_text(),
                "capacity": {
                    "active_sessions": active,
                    "max_normal": self.MAX_NORMAL,
                    "max_reject": self.MAX_REJECT,
                    "mode": mode,
                    "queued_requests": self.queued_requests,
                    "rejected_requests": self.rejected_requests,
                    "queue_depth": len(self.request_queue),
                    "load_pct": round(min(100.0, (active / self.MAX_REJECT) * 100), 1),
                },
                "metrics": {
                    "cpu_pct": round(self.cpu_sim_pct, 1),
                    "ram_pct": round(self.ram_sim_pct, 1),
                    "rpm": len(self._request_timestamps),
                    "bandwidth_bytes_s": self.bw_bytes_s,
                    "failed_logins": self.failed_logins,
                    "incident_count": self.incident_count,
                    "high_latency_clients": high_latency_clients,
                },
                "sessions": sessions,
                "active_alerts": list(self.active_alerts),
                "last_diagnosis": self.last_diagnosis,
                # NEW: executed actions visible on dashboard
                "executed_actions": list(self.executed_actions)[:20],
                "blacklisted_ips": list(self.blacklisted_ips),
                "cpu_throttle_active": self.cpu_throttle_active,
            }
