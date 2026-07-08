"""BaseAgent — shared foundation for all NetGuard AI specialist agents.

Each agent:
  1. Always runs heuristic analysis (zero API calls, instant)
  2. Optionally calls Gemini if: first occurrence OR heuristic confidence is LOW
  3. Caches diagnosis per alert key for 5 minutes (300s)
  4. Reports an AgentResult back to the orchestrator
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from logger import log


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_name: str
    alert_key: str
    alert_reason: str
    severity: str          # Low / Medium / High / Critical
    root_cause: str
    immediate_action: str
    preventive_measures: list[str]
    confidence: str        # Heuristic / Gemini / Heuristic+Gemini
    resolved: bool
    escalation_needed: bool
    ai_meta: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "alert_key": self.alert_key,
            "alert_reason": self.alert_reason,
            "severity": self.severity,
            "root_cause": self.root_cause,
            "immediate_action": self.immediate_action,
            "preventive_measures": self.preventive_measures,
            "confidence": self.confidence,
            "resolved": self.resolved,
            "escalation_needed": self.escalation_needed,
            "ai_meta": self.ai_meta,
            "timestamp": self.timestamp,
        }


# ── BaseAgent ─────────────────────────────────────────────────────────────────

class BaseAgent:
    """Subclass this and implement `_heuristic(alert)` and optionally `_gemini_prompt(alert)`."""

    CACHE_TTL = int(os.getenv("AGENT_CACHE_TTL", "45"))
    GEMINI_DAILY_LIMIT = int(os.getenv("GEMINI_DAILY_LIMIT", "25"))
    GEMINI_MIN_INTERVAL_SECONDS = int(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "45"))
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    _gemini_calls_today = 0
    _gemini_day = ""
    _gemini_last_call_by_key: dict[str, float] = {}

    def __init__(self, name: str) -> None:
        self.name = name
        self._cache: dict[str, tuple[float, AgentResult]] = {}  # key → (ts, result)

    # ── Public ──────────────────────────────────────────────────────────────

    def analyse(self, alert: dict[str, Any], api_key: str | None) -> AgentResult:
        key = alert.get("key", "unknown")
        ai_meta = {
            "api_key_present": bool(api_key),
            "cache_hit": False,
            "attempted": False,
            "used": False,
            "source": "heuristic",
            "skip_reason": "",
            "error": "",
        }

        # Check cache
        cached = self._cache.get(key)
        if cached:
            age = time.time() - cached[0]
            if age < self.CACHE_TTL:
                log(self.name, f"Cache hit for {key} (age {age:.0f}s) - skipping API call")
                result = cached[1]
                result.ai_meta.update({
                    "cache_hit": True,
                    "source": "cache",
                    "skip_reason": "cache_ttl_active",
                })
                return result

        # Always run heuristic first
        result = self._heuristic(alert)
        result.ai_meta = ai_meta
        log(self.name, f"Heuristic for {key}: {result.severity} - {result.root_cause[:60]}")

        # Call Gemini only when unresolved high-signal alerts need deeper reasoning.
        budget_key = f"{self.name}:{key}"
        if api_key and result.confidence == "Heuristic" and self._should_call_gemini(result):
            if not self._gemini_budget_available(budget_key):
                log(self.name, "Gemini budget/cooldown reached, using heuristic result")
                result.ai_meta.update({
                    "skip_reason": "budget_or_cooldown",
                })
                self._cache[key] = (time.time(), result)
                return result
            try:
                result.ai_meta.update({"attempted": True})
                gemini_data = self._call_gemini(api_key, alert)
                if gemini_data:
                    result = self._merge(result, gemini_data, alert)
                    result.ai_meta.update({
                        "attempted": True,
                        "used": True,
                        "source": "gemini",
                        "skip_reason": "",
                    })
                    log(self.name, f"Gemini enriched diagnosis for {key}")
                else:
                    result.ai_meta.update({
                        "attempted": True,
                        "skip_reason": "empty_gemini_payload",
                    })
            except Exception as exc:
                result.ai_meta.update({
                    "attempted": True,
                    "skip_reason": "gemini_error",
                    "error": str(exc),
                })
                log(self.name, f"Gemini unavailable (using heuristic only): {exc}")
        elif not api_key:
            result.ai_meta.update({"skip_reason": "missing_api_key"})
        elif not self._should_call_gemini(result):
            result.ai_meta.update({"skip_reason": "heuristic_sufficient"})

        # Store in cache
        self._cache[key] = (time.time(), result)
        return result

    # ── Override these in subclasses ─────────────────────────────────────────

    def _heuristic(self, alert: dict[str, Any]) -> AgentResult:
        raise NotImplementedError

    def _gemini_prompt(self, alert: dict[str, Any]) -> str:
        raise NotImplementedError

    # ── Internals ─────────────────────────────────────────────────────────────

    def _should_call_gemini(self, result: AgentResult) -> bool:
        """Only escalate to Gemini for Medium/High/Critical severity not already resolved."""
        return result.severity in ("Medium", "High", "Critical") and not result.resolved

    @classmethod
    def _gemini_budget_available(cls, budget_key: str) -> bool:
        today = str(date.today())
        if cls._gemini_day != today:
            cls._gemini_day = today
            cls._gemini_calls_today = 0
            cls._gemini_last_call_by_key = {}

        if cls._gemini_calls_today >= cls.GEMINI_DAILY_LIMIT:
            return False

        last = cls._gemini_last_call_by_key.get(budget_key, 0.0)
        if (time.time() - last) < cls.GEMINI_MIN_INTERVAL_SECONDS:
            return False

        cls._gemini_calls_today += 1
        cls._gemini_last_call_by_key[budget_key] = time.time()
        return True

    @classmethod
    def gemini_status(cls) -> dict[str, Any]:
        today = str(date.today())
        if cls._gemini_day != today:
            return {
                "day": today,
                "daily_limit": cls.GEMINI_DAILY_LIMIT,
                "used_today": 0,
                "remaining": cls.GEMINI_DAILY_LIMIT,
                "min_interval_seconds": cls.GEMINI_MIN_INTERVAL_SECONDS,
            }
        used = cls._gemini_calls_today
        return {
            "day": cls._gemini_day,
            "daily_limit": cls.GEMINI_DAILY_LIMIT,
            "used_today": used,
            "remaining": max(0, cls.GEMINI_DAILY_LIMIT - used),
            "min_interval_seconds": cls.GEMINI_MIN_INTERVAL_SECONDS,
        }

    def _call_gemini(self, api_key: str, alert: dict[str, Any]) -> dict[str, Any] | None:
        import urllib.request, urllib.error
        prompt = self._gemini_prompt(alert)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.25, "maxOutputTokens": 800},
        }
        body = json.dumps(payload).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.GEMINI_MODEL}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode())
                raw = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_json(raw)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    time.sleep(2)
                    continue
                raise
        return None

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        import re
        cleaned = re.sub(r"```(?:json)?", "", raw or "").replace("```", "").strip()
        extracted = "{}"
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            extracted = match.group(0)
        for candidate in [cleaned, extracted]:
            try:
                return json.loads(candidate)
            except Exception:
                continue
        return {}

    def _merge(self, base: AgentResult, gemini: dict[str, Any], alert: dict[str, Any]) -> AgentResult:
        """Merge Gemini's enriched data into the heuristic result."""
        return AgentResult(
            agent_name=self.name,
            alert_key=alert.get("key", "unknown"),
            alert_reason=alert.get("reason", ""),
            severity=gemini.get("severity", base.severity),
            root_cause=gemini.get("root_cause", base.root_cause),
            immediate_action=gemini.get("immediate_action", base.immediate_action),
            preventive_measures=gemini.get("preventive_measures", base.preventive_measures),
            confidence="Heuristic+Gemini",
            resolved=gemini.get("resolved", base.resolved),
            escalation_needed=gemini.get("escalation_needed", base.escalation_needed),
        )
