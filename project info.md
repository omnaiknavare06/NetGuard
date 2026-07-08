# NetGuard AI — Complete Documentation (0 → 100)
### AI-Assisted Automated Network Monitoring and Troubleshooting System
> Version 2.0 | Python + Flask + Gemini 2.0 Flash | Educational Prototype

---

## TABLE OF CONTENTS

1. [Project Overview](#1-project-overview)
2. [System Architecture (Full Diagram)](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [File Structure](#4-file-structure)
5. [Module Deep-Dive](#5-module-deep-dive)
   - 5.1 logger.py
   - 5.2 state_manager.py
   - 5.3 task_simulator.py
   - 5.4 executor.py
   - 5.5 ai_engine.py
   - 5.6 monitor.py
   - 5.7 app.py
6. [All API Endpoints](#6-all-api-endpoints)
7. [All Client Tasks (10 Types)](#7-all-client-tasks)
8. [Capacity Management System](#8-capacity-management)
9. [Monitoring Conditions & Thresholds](#9-monitoring-conditions)
10. [AI Pipeline — The Full Recursive Loop](#10-ai-pipeline)
11. [Command Execution Engine](#11-command-execution)
12. [Latency Tracking System](#12-latency-tracking)
13. [Incident Report System](#13-incident-reports)
14. [Server-Sent Events (SSE) Real-Time Dashboard](#14-sse-real-time)
15. [Setup Guide (Step by Step)](#15-setup-guide)
16. [Testing Guide — How to Trigger Everything](#16-testing-guide)
17. [Data Flow Walkthroughs (End to End)](#17-data-flow)
18. [Security Considerations](#18-security)
19. [Common Issues & Fixes](#19-common-issues)
20. [Glossary](#20-glossary)

---

## 1. Project Overview

NetGuard AI is an educational simulation of an **intelligent network monitoring system**.
It demonstrates how AI (Google Gemini) can be integrated into a real-time server to:

- Detect abnormal network conditions automatically
- Diagnose problems using real diagnostic commands
- Provide root cause analysis and actionable recommendations
- Handle capacity limits, latency spikes, and attack scenarios

### What makes this different from a basic Flask app?

| Basic Flask App | NetGuard AI |
|---|---|
| Just serves HTTP requests | Monitors itself while serving |
| No awareness of server state | Tracks CPU, RAM, latency, sessions, bandwidth |
| Static responses | Triggers AI analysis when something goes wrong |
| No capacity management | Enforces 3-tier capacity (Normal / Degraded / Reject) |
| No diagnostics | Runs real `netstat`, `ping`, `traceroute` commands |
| No incident history | Saves every incident as a JSON report |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTS                                   │
│   Phones / Browsers → http://<SERVER_IP>:5000/client            │
│                                                                  │
│   10 Task Types:                                                 │
│   login  logout  db_query  file_upload  file_download           │
│   compute  search  stream  bulk_process  heartbeat              │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP POST /api/task/<name>
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FLASK SERVER (app.py)                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              STATE MANAGER (state_manager.py)            │   │
│  │                                                          │   │
│  │  sessions{}  |  failed_logins  |  cpu_sim  |  ram_sim   │   │
│  │  request_queue  |  rpm  |  bw_bytes_s  |  active_alerts │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────┐    ┌────────────────────────────────┐    │
│  │ TASK SIMULATOR   │    │   MONITOR ENGINE (monitor.py)  │    │
│  │ (task_simulator) │    │                                │    │
│  │                  │    │  Runs every 3 seconds in       │    │
│  │ Processes tasks  │    │  background thread.            │    │
│  │ Updates CPU/RAM  │    │  Checks 8 conditions:          │    │
│  │ Simulates delay  │    │  - failed logins               │    │
│  │ based on load    │    │  - capacity (10/14/15 tiers)   │    │
│  └──────────────────┘    │  - CPU > 80%                   │    │
│                          │  - RAM > 85%                   │    │
│                          │  - RPM > 80                    │    │
│                          │  - bandwidth > 5MB/s           │    │
│                          │  - client latency > 1500ms     │    │
│                          └──────────────┬─────────────────┘    │
└─────────────────────────────────────────┼───────────────────────┘
                                          │ alert dict
                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AI ENGINE (ai_engine.py)                      │
│                                                                  │
│  ┌─ ITERATION 1 ────────────────────────────────────────────┐  │
│  │  Phase 1: Send alert context to Gemini 2.0 Flash         │  │
│  │           → Gemini returns: suggested command + reason   │  │
│  │  Phase 2: Run command via executor.py                    │  │
│  │           → Real output captured                         │  │
│  │  Phase 3: Send output back to Gemini                     │  │
│  │           → Gemini returns: root_cause, severity,        │  │
│  │             resolved?, immediate_action, measures        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  If resolved=false AND iterations < 3:                          │
│  ┌─ ITERATION 2 ────────────────────────────────────────────┐  │
│  │  Phase 1: Gemini shown previous action, suggests NEW cmd │  │
│  │  Phase 2: Run new command                                │  │
│  │  Phase 3: Analyze new output                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  (Up to 3 iterations maximum)                                   │
└──────────────────────────────────────────┬──────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────┐
                    │           EXECUTOR (executor.py)         │
                    │                                          │
                    │  Whitelist: ping, netstat, traceroute,   │
                    │  nslookup, ipconfig, arp, route, who     │
                    │                                          │
                    │  subprocess.run() with 25s timeout      │
                    │  OS-aware (Windows/Linux/macOS)         │
                    └──────────────────────────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────┐
                    │         LOGGER + INCIDENT STORE          │
                    │                                          │
                    │  logs/system.log    (all events)         │
                    │  incidents/*.json   (per incident)       │
                    └──────────────────────────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────┐
                    │        ADMIN DASHBOARD (SSE stream)      │
                    │                                          │
                    │  http://localhost:5000                   │
                    │                                          │
                    │  - Capacity gauge (live)                 │
                    │  - Per-client session table              │
                    │  - AI diagnosis with all iterations      │
                    │  - Incident history                      │
                    │  - Color-coded live log stream           │
                    └──────────────────────────────────────────┘
```

---

## 3. Technology Stack

| Component | Technology | Why |
|---|---|---|
| Web server | **Flask 3.x** | Lightweight, easy multi-threading |
| AI analysis | **Gemini 2.0 Flash** (free tier) | Fast, free, structured JSON output |
| HTTP to Gemini | **urllib** (stdlib) | Zero extra dependencies |
| Real-time dashboard | **Server-Sent Events (SSE)** | No WebSocket needed, works everywhere |
| Command execution | **subprocess** (stdlib) | Safe, cross-platform |
| Threading | **threading** (stdlib) | Background monitor + AI pipeline |
| Logging | Custom file + stdout | Timestamps, color-coded by category |
| Incident storage | JSON files | Human-readable, no database needed |
| Frontend | Vanilla JS + CSS | No React/Vue needed, runs on phones |

---

## 4. File Structure

```
netguard/
│
├── app.py               ← Flask server entry point
│                          All HTTP routes defined here
│                          Starts monitor thread on startup
│                          SSE broadcaster
│
├── state_manager.py     ← Central brain of the system
│                          Thread-safe StateManager class
│                          Tracks sessions, metrics, alerts
│                          Capacity enforcement (3 tiers)
│
├── task_simulator.py    ← Simulates 10 server-side tasks
│                          Each task has CPU/RAM/latency costs
│                          Scales delay with server load
│
├── monitor.py           ← Background surveillance thread
│                          Polls state every 3 seconds
│                          Checks 8 alert conditions
│                          Triggers AI pipeline when needed
│
├── ai_engine.py         ← Gemini 2.0 Flash integration
│                          3-phase recursive diagnostic loop
│                          Structured JSON prompts/responses
│
├── executor.py          ← Safe diagnostic command runner
│                          Whitelist of 8 commands
│                          OS-aware (Windows/Linux/macOS)
│                          subprocess with timeout
│
├── logger.py            ← Structured logging system
│                          File + color-coded terminal output
│                          Incident JSON report saver
│
├── requirements.txt     ← Just: flask>=3.0.0
│
├── logs/
│   └── system.log       ← All events with timestamps
│
├── incidents/
│   └── incident_*.json  ← Per-incident detailed reports
│
└── templates/
    ├── dashboard.html   ← Admin console (cyberpunk UI)
    └── client.html      ← Client task simulator
```

---

## 5. Module Deep-Dive

### 5.1 logger.py

**Purpose:** Write structured log entries to a file AND print them color-coded to terminal.

**Key functions:**

```python
log(category, message)
```
- Writes `[YYYY-MM-DD HH:MM:SS] [CATEGORY  ] message`
- Categories and their colors:
  - `SYSTEM`   → grey (startup messages)
  - `CLIENT`   → cyan (session joins/leaves, task calls)
  - `MONITOR`  → yellow (alert detections)
  - `AI`       → blue (Gemini API calls)
  - `EXECUTOR` → green (command runs + output)
  - `PIPELINE` → magenta (iteration progress)
  - `CAPACITY` → red (rejections, queuing)
  - `LATENCY`  → bright yellow (latency alerts)
  - `TASK`     → bright cyan (task processing)
  - `INCIDENT` → bright red (incident saves)

```python
read_logs(limit=200) → list[str]
```
- Reads last N lines from system.log
- Used by `/api/logs` endpoint → displayed on dashboard

```python
save_incident(incident: dict) → str
```
- Saves full incident dict as `incidents/incident_YYYYMMDD_HHMMSS.json`
- Returns the filename

```python
load_incidents(limit=20) → list[dict]
```
- Reads last N incident JSON files
- Used by `/api/incidents` endpoint

---

### 5.2 state_manager.py

**Purpose:** The single source of truth for all server state. Thread-safe.

**Class: `StateManager`**

**Data it maintains:**

```python
sessions = {
  "client_id": {
    "ip": "192.168.1.5",
    "joined_at": "2024-01-01 12:00:00",
    "degraded": False,        # True if joined during overload
    "current_task": "db_query",
    "task_count": 15,
    "error_count": 2,
    "latency_history": deque([120, 250, 310, ...], maxlen=10),
    "last_seen": 1704067200.0  # unix timestamp
  }
}

request_queue  = deque(maxlen=50)   # queued connection requests
failed_logins  = 0                  # total failed login attempts
cpu_sim_pct    = 15.0               # simulated CPU %
ram_sim_pct    = 25.0               # simulated RAM %
bw_bytes_s     = 0                  # bandwidth bytes/second
active_alerts  = [...]              # recent alert dicts
last_diagnosis = {...}              # latest AI diagnosis
incident_count = 0                  # total incidents triggered
```

**Capacity logic in `try_join()`:**

```
if client_id already in sessions → return "ok" (already connected)

if active >= 15 (MAX_REJECT):
    rejected_requests += 1
    return {"status": "rejected", "message": "Server full"}

if active >= 10 (MAX_NORMAL, but < 15):
    queued_requests += 1
    add to request_queue
    add session with degraded=True
    return {"status": "queued"}

else (active < 10):
    add session normally
    return {"status": "ok"}
```

**`_natural_decay()`:** Called every monitor sweep. CPU and RAM slowly decrease toward a baseline proportional to active sessions. This simulates tasks finishing.

**`snapshot()`:** Returns a complete, JSON-serializable dict of current state. Used by `/api/state` and the monitor engine.

---

### 5.3 task_simulator.py

**Purpose:** Simulate 10 realistic server-side tasks with different resource costs.

**Task profiles table:**

| Task | CPU cost | RAM cost | Base delay | Max jitter | Payload size |
|---|---|---|---|---|---|
| login | 3% | 1% | 80ms | 60ms | 256 B |
| logout | 1% | 0% | 20ms | 10ms | 64 B |
| db_query | 18% | 12% | 300ms | 400ms | 512 B |
| file_upload | 8% | 25% | 400ms | 600ms | 5 MB |
| file_download | 6% | 15% | 250ms | 300ms | 500 KB |
| compute | 35% | 8% | 800ms | 1200ms | 1 KB |
| search | 12% | 6% | 200ms | 300ms | 384 B |
| stream | 10% | 20% | 600ms | 800ms | 2 MB |
| bulk_process | 40% | 30% | 1200ms | 2000ms | 10 MB |
| heartbeat | 0.5% | 0% | 10ms | 5ms | 64 B |

**Overload scaling:**
```
overload_factor = 1.0
if active_sessions > 10:
    overload_factor += (active - 10) * 0.3   # +30% per extra client
```
→ With 15 active clients: `overload_factor = 1.0 + 5*0.3 = 2.5`
→ A db_query that normally takes 300ms now takes 750ms
→ This causes latency alerts on the monitoring dashboard

**Error simulation:**
- If `overload_factor > 1.8` AND random chance < 15% → task fails
- This simulates server errors under load

---

### 5.4 executor.py

**Purpose:** Safely execute diagnostic network commands suggested by AI.

**Whitelist (8 commands):**

| Command | Linux/Mac | Windows | Purpose |
|---|---|---|---|
| ping | ping -c 4 {target} | ping -n 4 {target} | Test reachability, RTT |
| netstat | ss -tunapo | netstat -an | Show all connections |
| traceroute | traceroute -m 10 {target} | tracert -h 10 {target} | Trace packet route |
| nslookup | nslookup {target} | nslookup {target} | DNS resolution |
| ipconfig | ip addr show | ipconfig /all | Network interfaces |
| arp | arp -n | arp -a | IP ↔ MAC mapping |
| route | ip route show | route print | Routing table |
| who | who | query session | Logged-in users |

**Safety guarantees:**
- ONLY commands in COMMANDS dict can run
- `{target}` is the only variable substitution (no shell injection)
- 25-second timeout on every command
- stderr and stdout both captured
- `FileNotFoundError` handled gracefully (command not installed)

**`parse_from_ai_text(text)`:**
- Scans AI response for a command name
- Returns the first match found in the whitelist
- Fallback: returns None → caller defaults to "netstat"

---

### 5.5 ai_engine.py

**Purpose:** Interface with Gemini 2.0 Flash to run the 3-phase diagnostic loop.

**`_call(api_key, prompt)`:**
- Pure stdlib urllib POST request
- Model: `gemini-2.0-flash`
- Temperature: 0.3 (focused, consistent responses)
- Max tokens: 1000
- Auto-retry on HTTP 429 (rate limit) with exponential backoff

**`_parse_json(raw, fallback)`:**
- Strips markdown code fences (```json ... ```)
- Tries `json.loads()` on full response
- Falls back to extracting first `{...}` block
- Uses `fallback` dict if all parsing fails

**Phase 1 — `suggest_command(api_key, alert, iteration, previous_actions)`:**

Prompt includes:
- Current alert reason
- Server metrics (CPU, RAM, RPM, sessions, latency clients)
- Previous iterations already run (so AI doesn't repeat itself)
- Available command list

Gemini returns JSON:
```json
{
  "command": "netstat",
  "target": "8.8.8.8",
  "reason": "Multiple connections may indicate port scanning",
  "suspected_issue": "Possible port scan or DDoS attempt",
  "risk_level": "High"
}
```

**Phase 2 — `analyze_output(api_key, cmd_name, cmd_output, alert, iteration)`:**

Prompt includes:
- The command that was run
- Full command output (truncated to 1800 chars)
- Original alert context

Gemini returns JSON:
```json
{
  "root_cause": "Multiple SYN connections from single IP",
  "explanation": "The netstat output shows 47 connections...",
  "severity": "High",
  "resolved": false,
  "immediate_action": "Block IP 192.168.1.99 via firewall",
  "preventive_measures": [
    "Enable SYN flood protection",
    "Configure rate limiting per IP",
    "Set up fail2ban"
  ],
  "escalation_needed": true
}
```

**`run_pipeline(api_key, alert)`:**

```
Loop up to 3 times:
  1. suggest_command() → get command + target
  2. executor.execute(command, target) → get output
  3. analyze_output() → get diagnosis
  4. if diagnosis["resolved"] == True → break
  5. else → continue with previous_actions list
Returns: complete incident dict with all iterations
```

---

### 5.6 monitor.py

**Purpose:** Background daemon thread that continuously watches server state.

**How it runs:**
```python
monitor.start(api_key)
# Creates a daemon thread that calls _sweep() every POLL_INTERVAL seconds
# POLL_INTERVAL = 3 (seconds)
```

**`_sweep(api_key)`:**
1. Calls `state._natural_decay()` → reduce CPU/RAM toward baseline
2. Calls `state.snapshot()` → get current state
3. Calls `_check_conditions(snap)` → find triggered alerts
4. If alerts found: logs them, calls `_run_ai_if_ready()`

**8 monitored conditions:**

| Condition Key | Trigger | Default Threshold |
|---|---|---|
| `failed_login` | failed_logins >= 5 | 5 attempts |
| `capacity_degrade` | active > 10 | 11+ sessions |
| `capacity_critical` | active >= 14 | 14+ sessions |
| `cpu_high` | cpu_sim_pct >= 80 | 80% |
| `ram_high` | ram_sim_pct >= 85 | 85% |
| `rpm_high` | rpm >= 80 | 80 req/min |
| `bandwidth_high` | bw_bytes_s >= 5MB | 5,000,000 B/s |
| `latency_high` | any client avg > 1500ms | 1500ms |

**Cooldowns:**
- Each condition has its own 20-second cooldown (`_alert_cooldowns`)
- Global AI pipeline cooldown: 45 seconds (`AI_COOLDOWN`)
- Prevents alert spam and Gemini API overuse

---

### 5.7 app.py

**Purpose:** Flask entry point. Defines all routes, starts monitor, manages SSE.

**Startup sequence:**
```python
1. Create logs/ and incidents/ directories
2. Check for GEMINI_API_KEY
3. monitor.start(GEMINI_API_KEY)  → background thread
4. Start SSE state-pusher thread  → broadcasts every 3s
5. app.run(host="0.0.0.0", port=5000, threaded=True)
```

**SSE broadcaster:**
```python
_sse_queue = queue.Queue(maxsize=200)

def _broadcast(event_type, data):
    _sse_queue.put_nowait({"type": event_type, "data": data})
```
Called after every task, join, leave, simulation. Dashboard receives these instantly.

---

## 6. All API Endpoints

### Client endpoints:

| Method | URL | Body | Returns |
|---|---|---|---|
| POST | `/api/join` | `{client_id}` | `{status, message}` |
| POST | `/api/leave` | `{client_id}` | `{status, message}` |
| POST | `/api/task/<name>` | `{client_id}` | task result |
| POST | `/api/task/login` | `{client_id, success}` | auth result |

### Admin endpoints:

| Method | URL | Body | Returns |
|---|---|---|---|
| GET | `/api/state` | – | full snapshot dict |
| GET | `/api/logs?limit=200` | – | `{logs: [...]}` |
| GET | `/api/incidents` | – | `{incidents: [...]}` |
| GET | `/api/events` | – | SSE stream |
| POST | `/api/reset` | – | `{status: "ok"}` |

### Simulation (testing) endpoints:

| Method | URL | Body | Returns |
|---|---|---|---|
| POST | `/api/simulate/overload` | `{count: 8}` | sessions added |
| POST | `/api/simulate/attack` | `{count: 10}` | failed logins added |

### Pages:

| URL | Description |
|---|---|
| `GET /` | Admin dashboard |
| `GET /client` | Client simulator UI |

---

## 7. All Client Tasks

| Task Name | Endpoint | Simulates | Resource Impact |
|---|---|---|---|
| login | `/api/task/login` | User authentication | Low (cpu+3, ram+1) |
| logout | `/api/task/logout` | Session termination | Minimal |
| db_query | `/api/task/db_query` | SQL SELECT/JOIN | Medium (cpu+18, ram+12) |
| file_upload | `/api/task/file_upload` | Upload 5MB file | Medium (cpu+8, ram+25) |
| file_download | `/api/task/file_download` | Download 500KB | Medium |
| compute | `/api/task/compute` | Heavy calculation | HIGH (cpu+35) |
| search | `/api/task/search` | Full-text search | Medium (cpu+12) |
| stream | `/api/task/stream` | Video/data stream | Medium-high |
| bulk_process | `/api/task/bulk_process` | Batch job | VERY HIGH (cpu+40, ram+30) |
| heartbeat | `/api/task/heartbeat` | Ping/latency check | None |

**Failed login (special):**
- Same URL: `POST /api/task/login` with body `{"success": false}`
- Increments `state.failed_logins` counter
- Triggers brute-force alert when count reaches 5

---

## 8. Capacity Management

### The 3 Tiers:

```
Sessions 0–10  (GREEN)  → NORMAL OPERATION
├── All tasks processed at normal speed
├── Resources shared equally
└── New connections accepted immediately

Sessions 11–14 (YELLOW) → DEGRADED MODE
├── New connections accepted but flagged as "queued"
├── overload_factor = 1 + (active-10) × 0.3
├── Tasks take longer (30% extra per extra client)
├── Higher chance of simulated task errors
├── CAPACITY ALERT fired → monitor detects
└── AI pipeline triggered to investigate

Sessions 15+   (RED)    → CRITICAL / REJECT
├── ALL new connection requests REJECTED (HTTP 503)
├── rejected_requests counter increments
├── Client sees: "Server full. Try later."
├── CAPACITY CRITICAL ALERT fired
└── AI pipeline triggered immediately
```

### What gets tracked per session:
- Client ID and IP address
- When they joined
- Whether they're in degraded mode
- Their current task
- Total tasks completed
- Error count
- Last 10 latency measurements
- Last seen timestamp

### How to test capacity:
1. Open 10+ browser tabs of `/client` and press CONNECT in each
2. Or use the `⚡ SIM OVERLOAD` button on the admin dashboard
3. Watch the capacity gauge turn yellow → red

---

## 9. Monitoring Conditions

The monitor runs every 3 seconds. Each condition has a 20-second cooldown.

### Condition 1: Failed Login Threshold
```
failed_logins >= 5
Alert: "High failed login count (N attempts)"
What it means: Possible brute-force login attack
AI suggests: netstat (check connections) or who (check logged users)
```

### Condition 2: Capacity Degraded
```
active_sessions > 10
Alert: "Server in DEGRADED mode (N/14 sessions)"
What it means: Server handling more clients than optimal capacity
AI suggests: netstat (see all connections) or ipconfig
```

### Condition 3: Capacity Critical
```
active_sessions >= 14
Alert: "Server CRITICAL — rejecting new connections"
What it means: Server is rejecting clients, possibly under DDoS
AI suggests: netstat or arp (check suspicious IPs)
```

### Condition 4: CPU High
```
cpu_sim_pct >= 80%
Alert: "CPU usage critical (N%)"
What it means: Heavy tasks (compute, bulk) are saturating CPU
AI suggests: who or netstat
```

### Condition 5: RAM High
```
ram_sim_pct >= 85%
Alert: "RAM usage critical (N%)"
What it means: Memory-intensive tasks (stream, bulk) filling RAM
AI suggests: netstat or ping
```

### Condition 6: RPM High
```
requests_per_minute >= 80
Alert: "Request rate spike (N req/min)"
What it means: Request flood, possibly automated attack
AI suggests: netstat or arp
```

### Condition 7: Bandwidth High
```
bw_bytes_s >= 5,000,000 (5 MB/s)
Alert: "Bandwidth spike (N KB/s)"
What it means: Large file transfers or streaming overwhelming network
AI suggests: ping or traceroute
```

### Condition 8: Client Latency High
```
any client avg_latency > 1500ms
Alert: "High latency for clients: [client_id1, ...]"
What it means: Server overloaded, responses slow for specific clients
AI suggests: ping (check connectivity) or traceroute
```

---

## 10. AI Pipeline

### Complete Flow (with code references):

```
TRIGGER (monitor.py:_sweep)
    │
    ├─ _check_conditions() returns list of triggered conditions
    ├─ _build_alert_context() packages state into alert dict
    └─ _run_ai_if_ready() checks 45s cooldown then:

BACKGROUND THREAD (ai_engine.py:run_pipeline)
    │
    ├─ ITERATION 1
    │   ├─ suggest_command(api_key, alert, iteration=0, previous=[])
    │   │       ↓ Prompt sent to Gemini 2.0 Flash
    │   │   Gemini analyzes: alert_reason, cpu, ram, sessions, failed_logins
    │   │   Gemini returns: {"command":"netstat", "target":"8.8.8.8", ...}
    │   │       ↓
    │   ├─ executor.execute("netstat", "8.8.8.8")
    │   │   Real subprocess.run() on your laptop
    │   │   Output captured (actual netstat/ss output)
    │   │       ↓
    │   └─ analyze_output(api_key, "netstat", output, alert, iteration=0)
    │           ↓ Output + context sent to Gemini
    │       Gemini returns: {root_cause, severity, resolved, action, measures}
    │
    ├─ If resolved=True → DONE (write incident, update state)
    │
    ├─ ITERATION 2 (if not resolved)
    │   ├─ suggest_command(..., iteration=1, previous=[{iter1 data}])
    │   │   Gemini sees iter 1 already ran "netstat" → suggests DIFFERENT cmd
    │   ├─ executor.execute(new_command)
    │   └─ analyze_output(new output)
    │
    └─ ITERATION 3 (max)
        └─ Final result written regardless of resolved status

RESULT STORED (state_manager.py)
    state.last_diagnosis = {
        alert, iterations[...], final_diagnosis, resolved, timestamp
    }
    state.incident_count += 1

INCIDENT SAVED (logger.py)
    incidents/incident_YYYYMMDD_HHMMSS.json

DASHBOARD UPDATED (SSE push within 3 seconds)
```

### Why 3 iterations?
- Free Gemini API has rate limits
- Most issues are diagnosed in 1–2 iterations
- 3 iterations = 6 Gemini API calls per incident (reasonable)

### Why temperature 0.3?
- Lower temperature = more consistent, focused responses
- AI gives structured JSON instead of creative/verbose text
- Better for parsing

---

## 11. Command Execution Engine

### Safety model:
```
User/AI → says "run netstat"
              │
              ▼
executor.py checks: is "netstat" in COMMANDS dict?
    YES → look up OS-specific command string
          "ss -tunapo" (Linux) or "netstat -an" (Windows)
              │
              ▼
    subprocess.run(
        ["ss", "-tunapo"],   # list form, no shell=True on Linux/Mac
        capture_output=True,
        text=True,
        timeout=25,
        encoding="utf-8"
    )
              │
              ▼
    stdout + stderr captured
    Returns dict: {status, command, cmd_string, output, output_lines}
    
    NO → return {status: "blocked", output: "not in whitelist"}
```

### Why no `shell=True` on Linux?
- Prevents shell injection. If `shell=True` and someone passes `target="google.com; rm -rf /"` → disaster
- On Windows, `shell=True` is unavoidable for some commands but no variable substitution risk

### Timeout handling:
- 25 second timeout on all commands
- `subprocess.TimeoutExpired` caught gracefully
- Returns message to AI: "Command timed out" → AI adjusts recommendation

---

## 12. Latency Tracking

### How latency is measured:
```
Client sends POST /api/task/db_query
    │
    ├─ Flask receives request
    ├─ task_simulator.process() called
    │   t_start = time.time()
    │   ... actual task simulation (sleep + CPU math) ...
    │   elapsed_ms = (time.time() - t_start) * 1000
    │
    └─ state.record_task(client_id, task_name, elapsed_ms)
           stores elapsed_ms in sessions[client_id]["latency_history"]
           latency_history is deque(maxlen=10) → last 10 measurements
```

### How avg latency is calculated:
```python
hist = list(sessions[client_id]["latency_history"])
avg = sum(hist) / len(hist)
```

### When does latency increase?
1. More active sessions → `overload_factor` increases → tasks take longer
2. Heavy tasks (compute, bulk_process) compete for simulated CPU
3. Multiple clients streaming simultaneously → RAM pressure

### Dashboard display:
- Avg latency shown per client in session table
- Color coding: <600ms green, 600-1500ms yellow, >1500ms red

---

## 13. Incident Reports

Every time the AI pipeline completes, a JSON file is saved:

```json
{
  "incident_id": 3,
  "timestamp": "2024-01-15 14:32:07",
  "alert": {
    "reason": "High failed login count (8 attempts) | CPU usage critical (83.2%)",
    "active": 12,
    "max_capacity": 10,
    "cpu_pct": 83.2,
    "ram_pct": 71.5,
    "failed_logins": 8,
    "rpm": 45
  },
  "iterations": [
    {
      "iteration": 1,
      "command": "netstat",
      "target": "8.8.8.8",
      "cmd_string": "ss -tunapo",
      "cmd_output": "Netid  State   Recv-Q...",
      "suggestion": {
        "command": "netstat",
        "reason": "Check for suspicious connections",
        "suspected_issue": "Brute force attack",
        "risk_level": "High"
      },
      "diagnosis": {
        "root_cause": "Multiple failed SSH attempts from 192.168.1.99",
        "severity": "High",
        "resolved": false,
        "immediate_action": "Block IP via firewall"
      }
    },
    {
      "iteration": 2,
      "command": "who",
      ...
    }
  ],
  "final_diagnosis": {
    "root_cause": "...",
    "severity": "High",
    "resolved": true,
    "immediate_action": "...",
    "preventive_measures": [...]
  },
  "resolved": true,
  "total_iterations": 2
}
```

Files saved to: `incidents/incident_YYYYMMDD_HHMMSS.json`

---

## 14. SSE Real-Time Dashboard

### How SSE works:
```
Dashboard browser opens connection to GET /api/events
                    │
                    │ (keeps connection open)
                    │
Flask sends data whenever _broadcast() is called:
  "data: {\"type\":\"state\", \"data\":{...}}\n\n"
                    │
                    │
Dashboard JavaScript:
  const es = new EventSource('/api/events');
  es.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'state') renderState(msg.data);
  };
```

### When is state broadcast?
1. Every 3 seconds by background pusher thread
2. Immediately after `/api/join` or `/api/leave`
3. After every task completion
4. After simulations

### Fallback polling:
Even if SSE drops, dashboard polls `/api/state` every 3 seconds as backup.

---

## 15. Setup Guide

### Prerequisites:
- Python 3.10 or newer
- pip
- A free Google Gemini API key

### Step 1: Get Gemini API Key (FREE)
1. Go to: https://aistudio.google.com/app/apikey
2. Sign in with Google account
3. Click "Create API Key"
4. Copy the key

### Step 2: Install Flask
```bash
pip install flask
```

### Step 3: Set API Key

**Windows (Command Prompt):**
```cmd
set GEMINI_API_KEY=AIzaSy...your_key_here
```

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="AIzaSy...your_key_here"
```

**macOS / Linux:**
```bash
export GEMINI_API_KEY=AIzaSy...your_key_here
```

**To make it permanent (macOS/Linux):**
```bash
echo 'export GEMINI_API_KEY=AIzaSy...' >> ~/.bashrc
source ~/.bashrc
```

### Step 4: Run the server
```bash
cd netguard
python app.py
```

You should see:
```
[2024-01-15 12:00:00] [SYSTEM   ] ============================================================
[2024-01-15 12:00:00] [SYSTEM   ]   NetGuard AI — Network Monitoring System
[2024-01-15 12:00:00] [SYSTEM   ] ============================================================
[2024-01-15 12:00:00] [SYSTEM   ] Gemini API key found ✓
[2024-01-15 12:00:00] [MONITOR  ] Monitoring engine started (poll every 3s).
[2024-01-15 12:00:00] [SYSTEM   ] Server starting on http://0.0.0.0:5000
```

### Step 5: Open dashboard
Browser: `http://localhost:5000`

### Step 6: Connect phones (optional)
1. Find your laptop's local IP:
   - Windows: `ipconfig` → look for "IPv4 Address" under your WiFi adapter
   - macOS: `ifconfig en0 | grep inet`
   - Linux: `ip addr show | grep inet`
2. On phones connected to same WiFi:
   `http://192.168.1.X:5000/client` (replace X with your IP)

---

## 16. Testing Guide

### Test 1: Basic functionality
1. Open `http://localhost:5000/client`
2. Press CONNECT
3. Click any task button (e.g., DB QUERY)
4. Check admin dashboard at `http://localhost:5000`
5. See session appear in table, metrics update

### Test 2: Brute force detection
1. In client simulator: click **FAILED LOGIN** 5 times
2. OR click **🔒 BRUTE FORCE** (sends 10 at once)
3. Watch dashboard: MONITOR alert fires, AI pipeline starts
4. In ~30-60 seconds: AI diagnosis appears

### Test 3: Capacity overload
1. Admin dashboard: click **⚡ SIM OVERLOAD**
2. Watch capacity gauge go yellow/red
3. Monitoring detects capacity_degrade condition
4. AI pipeline triggered

### Test 4: CPU/RAM stress
1. Open client, press CONNECT
2. Click **⚙️ HEAVY COMPUTE** several times quickly
3. OR click **🧮 BULK PROCESS**
4. Watch CPU % rise in metrics
5. When it hits 80%, monitor triggers alert

### Test 5: Full pipeline observation
1. Open two tabs: dashboard + client
2. In client: click **⚡ CAPACITY FLOOD**
3. Watch in real time:
   - Capacity gauge fills up
   - MONITOR log lines appear (yellow)
   - PIPELINE log lines appear (magenta)
   - AI log lines appear (blue) as Gemini is queried
   - EXECUTOR log lines appear (green) as command runs
   - Diagnosis panel populates

### Test 6: Multi-phone test
1. Connect 3-4 phones to same WiFi
2. Each opens `/client` and connects
3. All hit BULK PROCESS simultaneously
4. Server enters degraded mode
5. Latency increases on all clients

### Test 7: Complete rejection test
1. Admin: click SIM OVERLOAD (adds 8 fake sessions)
2. Client: try to CONNECT from another device
3. Should get REJECTED (server at 15+ sessions)

---

## 17. Data Flow Walkthroughs

### Walk 1: Normal task execution
```
Phone browser: POST /api/task/db_query
  {"client_id": "cli_abc123"}
                │
                ▼ app.py:run_task()
state.snapshot() checks: cli_abc123 in sessions? YES
                │
                ▼ task_simulator.process("db_query", "cli_abc123")
snapshot: active=3 → overload_factor=1.0
delay = (300ms + rand(0,400ms)) * 1.0 = ~450ms
time.sleep(0.45)
state.update_resources(cpu_delta=18, ram_delta=12*0.3=3.6)
state.record_request(bytes_in=512)
state.record_task("cli_abc123", "db_query", 453ms)
                │
                ▼ Returns to phone:
{
  "status": "ok",
  "task": "db_query",
  "latency_ms": 453.2,
  "overload_factor": 1.0,
  "result": {"rows_returned": 23, "query_plan": "Index Scan on users"}
}
                │
                ▼ app.py broadcasts SSE:
_broadcast("metrics_update", state.snapshot()["metrics"])
                │
                ▼ Dashboard updates CPU/RAM/RPM in real time
```

### Walk 2: Anomaly → AI → Fix
```
[Monitor sweep at T=0]
state.snapshot() → cpu_sim_pct = 84.5%
_check_conditions() → "cpu_high" triggered (84.5 >= 80)

_alert_cooldowns["cpu_high"] not set yet → proceed

alert_context = {
  "reason": "CPU usage critical (84.5%)",
  "active": 8, "cpu_pct": 84.5, "ram_pct": 45.2, ...
}

state.active_alerts.append({...})
_run_ai_if_ready(api_key, alert_context)

[Background thread starts]

[T+1s] Phase 1 — Gemini asked:
  Prompt: "Server at 84.5% CPU, 8 clients, reason: CPU usage critical..."
  Response: {"command":"who","target":"8.8.8.8","reason":"Check for runaway processes","suspected_issue":"CPU exhaustion"}

[T+3s] executor.execute("who", "8.8.8.8")
  Linux: runs "who"
  Output: "user1 pts/0 2024-01-15 12:00"

[T+4s] Phase 2 — Gemini asked:
  Prompt: "Command 'who' output: [output]. Context: CPU 84.5%"
  Response: {
    "root_cause": "Intensive computational tasks from 8 concurrent users",
    "severity": "Medium",
    "resolved": false,
    "immediate_action": "Limit concurrent heavy tasks or increase CPU cores"
  }

[T+5s] resolved=false → Iteration 2

[T+6s] Phase 1 iter 2 — Gemini asked:
  Prompt includes: "Previously ran 'who', severity Medium, not resolved"
  Response: {"command":"netstat","reason":"Different cmd to check network load"}

[T+8s] executor.execute("netstat")
  Output: [netstat data]

[T+9s] Phase 2 iter 2 — Gemini:
  Response: {
    "root_cause": "Multiple bulk_process tasks competing for CPU",
    "severity": "Medium",
    "resolved": true,
    "immediate_action": "Queue bulk tasks, serve max 2 simultaneously"
    "preventive_measures": ["Task queue system", "Rate limiting per client", "CPU affinity"]
  }

[T+10s] resolved=true → Pipeline complete

state.last_diagnosis updated
state.incident_count += 1
logger.save_incident(full_incident_dict) → incidents/incident_*.json

Dashboard receives via SSE → AI Diagnosis panel populated
```

---

## 18. Security Considerations

This is an **educational prototype**. For production, you would also need:

1. **Authentication on admin routes** — Currently `/api/reset` and `/api/simulate/*` have no auth
2. **HTTPS** — Use nginx reverse proxy with SSL
3. **Gemini API key protection** — Use environment variables (already done) + vault in production
4. **Rate limiting on task endpoints** — Add per-IP limits with Flask-Limiter
5. **Input validation** — `client_id` from user body should be sanitized
6. **Command injection** — Currently safe (whitelist + no shell=True on Linux), but review if adding new commands
7. **CORS** — Currently allows all origins, restrict to known client IPs

---

## 19. Common Issues

| Problem | Likely Cause | Fix |
|---|---|---|
| AI pipeline never triggers | GEMINI_API_KEY not set | `export GEMINI_API_KEY=...` |
| "ping not found" in executor | ping binary not installed | Install iputils-ping (Linux) |
| Very slow task responses | Overloaded state not resetting | Click ↺ RESET on dashboard |
| Dashboard not updating | SSE blocked by proxy/firewall | Refresh page, SSE reconnects |
| Gemini returns "HTTP 429" | Rate limit hit | Wait 60s, AI cooldown handles it |
| Port 5000 already in use | Another Flask app running | `lsof -i :5000` then kill, or change port |
| Sessions not clearing | Left simulation sessions | Click ↺ RESET |
| netstat shows no output | ss not installed (some minimal Linux) | `apt install iproute2` |

---

## 20. Glossary

| Term | Meaning |
|---|---|
| **SSE** | Server-Sent Events. One-way push from server to browser. Used for real-time dashboard updates. |
| **Overload Factor** | Multiplier applied to task delays when server has >10 clients. Each extra client adds 30%. |
| **Degraded Mode** | Server state when 11-14 clients are active. New connections queued, responses slower. |
| **AI Pipeline** | The full process: alert → Gemini suggest → execute → Gemini analyze → (repeat if needed) |
| **Iteration** | One complete round of the AI pipeline (suggest + execute + analyze). Max 3 per incident. |
| **Simulated CPU/RAM** | Not real process metrics. Calculated from task costs. Used to trigger monitoring alerts. |
| **Whitelist** | Fixed list of safe commands executor will run. AI can only suggest from this list. |
| **Incident** | One complete AI pipeline run. Saved as JSON. Includes all iterations and final diagnosis. |
| **Cooldown** | Minimum time between repeated alert triggers. Prevents spam. Per-condition: 20s, global AI: 45s. |
| **Daemon thread** | Background thread that stops automatically when main program exits. Used for monitor + SSE pusher. |
| **RLock** | Reentrant lock. Thread-safe mechanism. Used by StateManager to prevent race conditions. |
| **RPM** | Requests Per Minute. Calculated using rolling window of last 60 seconds of request timestamps. |
| **Deque** | Double-ended queue with fixed maxlen. Used for latency history and request timestamps. |

---

*NetGuard AI — Educational Prototype*
*Built with Flask + Gemini 2.0 Flash*
*No real network is harmed. All resource metrics are simulated.*
