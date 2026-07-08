"""app.py — NetGuard AI Flask entry point."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from logger import clear_incidents, ensure_storage, incident_stats, load_incidents, log, read_logs
from monitor import MonitorEngine
from agents.base import BaseAgent
from state_manager import StateManager
from task_simulator import TASK_PROFILES, process_task

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS'] = False
state = StateManager()
subscribers: set[queue.Queue[str]] = set()
subscribers_lock = threading.Lock()


@app.errorhandler(500)
def handle_500(e):
    import traceback as tb
    return jsonify({"status": "error", "message": str(e), "traceback": tb.format_exc()}), 500


# ── SSE broadcast ────────────────────────────────────────────────────────────

def _do_broadcast(event_type: str, data: Any) -> None:
    """Inner broadcast — runs in a background thread, never raises."""
    try:
        message = f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"
        dead: list[queue.Queue[str]] = []
        with subscribers_lock:
            for sub in list(subscribers):
                try:
                    sub.put_nowait(message)
                except queue.Full:
                    dead.append(sub)
            for sub in dead:
                subscribers.discard(sub)
    except Exception:
        pass  # Never propagate broadcast errors to request handlers


def _broadcast(event_type: str, data: Any) -> None:
    """Fire-and-forget broadcast — always returns immediately."""
    threading.Thread(
        target=_do_broadcast,
        args=(event_type, data),
        daemon=True,
        name="ng-broadcast"
    ).start()


monitor = MonitorEngine(state, _broadcast)


def _state_pusher() -> None:
    while True:
        time.sleep(3)
        _broadcast("state", state.snapshot())


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() if fwd else request.remote_addr) or "unknown"


def _json_body() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


# ── Pages ────────────────────────────────────────────────────────────────────

@app.get("/")
def dashboard() -> str:
    return render_template("dashboard.html", tasks=list(TASK_PROFILES))


@app.get("/client")
def client() -> str:
    return render_template("client.html", tasks=list(TASK_PROFILES))


# ── API ──────────────────────────────────────────────────────────────────────

@app.post("/api/join")
def api_join() -> Response:
    try:
        body = _json_body()
        client_id = (body.get("client_id") or "").strip()
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"}), 400
        result = state.try_join(client_id, _client_ip())
        log("CLIENT", f"{client_id} join -> {result['status']}")
        _broadcast("state", state.snapshot())
        return jsonify(result), 200 if result["status"] != "rejected" else 503
    except Exception as exc:
        import traceback as tb
        log("SYSTEM", f"api_join error: {tb.format_exc()}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.post("/api/leave")
def api_leave() -> Response:
    try:
        body = _json_body()
        client_id = (body.get("client_id") or "").strip()
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"}), 400
        result = state.leave(client_id)
        log("CLIENT", f"{client_id} leave -> {result['status']}")
        _broadcast("state", state.snapshot())
        return jsonify(result), 200 if result["status"] == "ok" else 404
    except Exception as exc:
        import traceback as tb
        log("SYSTEM", f"api_leave error: {tb.format_exc()}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.post("/api/task/<task_name>")
def api_task(task_name: str) -> Response:
    body = _json_body()
    client_id = (body.get("client_id") or "").strip()
    if not client_id:
        return jsonify({"status": "error", "message": "client_id required"}), 400
    if not state.has_session(client_id):
        return jsonify({"status": "error", "message": "Connect first."}), 400
    if task_name not in TASK_PROFILES:
        return jsonify({"status": "error", "message": "Unknown task."}), 404
    login_success = bool(body.get("success", True))
    result = process_task(state, task_name, client_id, login_success=login_success)
    _broadcast("state", state.snapshot())
    _broadcast("task_result", {"client_id": client_id, **result})
    return jsonify(result), 200 if result["status"] in {"ok", "denied"} else 503


@app.get("/api/state")
def api_state() -> Response:
    return jsonify(state.snapshot())


@app.get("/api/logs")
def api_logs() -> Response:
    limit = int(request.args.get("limit", 200))
    return jsonify({"logs": read_logs(limit)})


@app.get("/api/incidents")
def api_incidents() -> Response:
    limit = int(request.args.get("limit", 20))
    return jsonify({"incidents": load_incidents(limit)})


@app.get("/api/incidents/export")
def api_incidents_export() -> Response:
    limit = int(request.args.get("limit", 100))
    return jsonify({
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": min(max(1, limit), 100),
        "incidents": load_incidents(limit),
    })


@app.post("/api/incidents/clear")
def api_incidents_clear() -> Response:
    removed = clear_incidents()
    log("SYSTEM", f"Cleared incident reports: {removed}")
    return jsonify({"status": "ok", "removed": removed})


@app.get("/api/agents")
def api_agents() -> Response:
    """Returns the live agent activity log for the dashboard."""
    return jsonify({"agents": monitor.get_agent_log()})


@app.get("/api/events")
def api_events() -> Response:
    def stream() -> Any:
        sub: queue.Queue[str] = queue.Queue(maxsize=100)
        with subscribers_lock:
            subscribers.add(sub)
        # Send initial state immediately (safe)
        try:
            snap = state.snapshot()
            sub.put_nowait(f"data: {json.dumps({'type': 'state', 'data': snap})}\n\n")
        except Exception:
            pass
        try:
            agents = monitor.get_agent_log()
            sub.put_nowait(f"data: {json.dumps({'type': 'agents', 'data': agents})}\n\n")
        except Exception:
            pass
        try:
            while True:
                try:
                    yield sub.get(timeout=15)
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            with subscribers_lock:
                subscribers.discard(sub)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/reset")
def api_reset() -> Response:
    state.reset()
    log("SYSTEM", "State reset from dashboard.")
    _broadcast("state", state.snapshot())
    return jsonify({"status": "ok"})


@app.post("/api/simulate/overload")
def api_simulate_overload() -> Response:
    body = _json_body()
    count = max(1, int(body.get("count", 8)))
    added = state.add_simulated_sessions(count)
    log("CAPACITY", f"Simulated {len(added)} sessions added")
    _broadcast("state", state.snapshot())
    return jsonify({"status": "ok", "added": added, "count": len(added)})


@app.post("/api/simulate/latency")
def api_simulate_latency() -> Response:
    body = _json_body()
    count = max(1, int(body.get("count", 3)))
    latency_ms = float(body.get("latency_ms", 1600.0))
    marked = state.inject_latency_spike(count=count, latency_ms=latency_ms)
    log("LATENCY", f"Injected latency spike for {len(marked)} session(s) at {int(latency_ms)}ms")
    _broadcast("state", state.snapshot())
    return jsonify({"status": "ok", "marked_clients": marked, "count": len(marked), "latency_ms": latency_ms})


@app.post("/api/simulate/attack")
def api_simulate_attack() -> Response:
    body = _json_body()
    count = int(body.get("count", 10))
    state.add_failed_logins(count)
    log("MONITOR", f"Simulated {count} failed logins added")
    _broadcast("state", state.snapshot())
    return jsonify({"status": "ok", "count": count})


@app.get("/api/actions")
def api_actions() -> Response:
    """Return the latest executed actions log."""
    snap = state.snapshot()
    return jsonify({
        "actions": snap.get("executed_actions", []),
        "blacklisted_ips": snap.get("blacklisted_ips", []),
        "cpu_throttle_active": snap.get("cpu_throttle_active", False),
    })


@app.get("/api/health")
def api_health() -> Response:
    snap = state.snapshot()
    s = incident_stats()
    return jsonify({
        "status": "ok",
        "timestamp": snap["timestamp"],
        "monitor_thread_alive": bool(monitor._thread and monitor._thread.is_alive()),
        "capacity_mode": snap["capacity"]["mode"],
        "active_sessions": snap["capacity"]["active_sessions"],
        "incident_files": s["total"],
    })


@app.get("/api/stats")
def api_stats() -> Response:
    snap = state.snapshot()
    return jsonify({
        "capacity": snap["capacity"],
        "metrics": snap["metrics"],
        "incident_files": incident_stats(),
        "executed_actions": len(snap.get("executed_actions", [])),
        "blacklisted_ips": len(snap.get("blacklisted_ips", [])),
    })


@app.post("/api/config/capacity")
def api_config_capacity() -> Response:
    body = _json_body()
    max_normal = body.get("max_normal")
    max_reject = body.get("max_reject")
    try:
        updated = state.update_capacity_limits(max_normal=max_normal, max_reject=max_reject)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    log("SYSTEM", f"Capacity limits updated: normal={updated['max_normal']} reject={updated['max_reject']}")
    _broadcast("state", state.snapshot())
    return jsonify({"status": "ok", **updated})


@app.get("/api/ai/report")
def api_ai_report() -> Response:
    incidents = load_incidents(100)
    total = len(incidents)
    gemini = 0
    heuristic = 0
    unresolved = 0
    by_agent: dict[str, int] = {}
    total_commands = 0
    total_actions = 0
    ai_skip_reasons: dict[str, int] = {}
    ai_errors: dict[str, int] = {}
    for incident in incidents:
        diagnosis = incident.get("final_diagnosis", {})
        confidence = str(diagnosis.get("confidence", ""))
        if "Gemini" in confidence:
            gemini += 1
        else:
            heuristic += 1
        if not bool(diagnosis.get("resolved", incident.get("resolved", False))):
            unresolved += 1
        for agent in incident.get("agents_used", []):
            by_agent[agent] = by_agent.get(agent, 0) + 1
        total_commands += int(incident.get("total_commands", 0))
        total_actions += int(incident.get("total_actions", 0))
        for result in incident.get("agent_results", []):
            meta = result.get("ai_meta", {}) if isinstance(result, dict) else {}
            reason = str(meta.get("skip_reason", "")).strip()
            if reason:
                ai_skip_reasons[reason] = ai_skip_reasons.get(reason, 0) + 1
            err = str(meta.get("error", "")).strip()
            if err:
                ai_errors[err] = ai_errors.get(err, 0) + 1
    return jsonify({
        "window": "latest_100_incidents",
        "total_incidents": total,
        "gemini_enriched": gemini,
        "heuristic_only": heuristic,
        "unresolved": unresolved,
        "resolved": max(0, total - unresolved),
        "agent_usage": by_agent,
        "total_actions": total_actions,
        "total_commands": total_commands,
        "ai_skip_reasons": ai_skip_reasons,
        "ai_errors": ai_errors,
        "gemini_budget": BaseAgent.gemini_status(),
        "latest_incident": incidents[0] if incidents else None,
    })


@app.get("/api/ai/status")
def api_ai_status() -> Response:
    return jsonify({"status": "ok", "gemini": BaseAgent.gemini_status()})


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap() -> None:
    ensure_storage()
    api_key = os.getenv("GEMINI_API_KEY")
    log("SYSTEM", "=" * 60)
    log("SYSTEM", "  NetGuard AI - Multi-Agent Network Monitor")
    log("SYSTEM", "=" * 60)
    log("SYSTEM", f"Gemini API: {'ENABLED' if api_key else 'DISABLED (heuristic-only mode)'}")
    log("SYSTEM", "Agents: SecurityAgent | CapacityAgent | PerformanceAgent | LatencyAgent")
    monitor.start(api_key)
    threading.Thread(target=_state_pusher, daemon=True, name="netguard-sse-pusher").start()


# When running directly via "python app.py", bootstrap and serve.
# When imported by run.py, bootstrap() is called explicitly from there.
if __name__ == "__main__":
    bootstrap()
    log("SYSTEM", "Server starting on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
