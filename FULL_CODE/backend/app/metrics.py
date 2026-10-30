"""In-process request metrics: per-route counts, error rates and latency percentiles.

Kept in memory (no extra dependency or service); resets when the process restarts. Routes are
keyed by their path template (e.g. /api/uploads/{uid}), never the concrete URL, so ids and
query strings cannot inflate the key space or leak into the metrics."""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_WINDOW = 500  # latency samples kept per route for percentiles

_lock = threading.Lock()
_started = time.time()
_routes: dict[str, dict[str, Any]] = {}


def observe(method: str, route: str, status: int, ms: float) -> None:
    key = f"{method} {route}"
    with _lock:
        r = _routes.get(key)
        if r is None:
            r = _routes[key] = {"count": 0, "client_errors": 0, "server_errors": 0, "total_ms": 0.0, "max_ms": 0.0,
                                "samples": deque(maxlen=_WINDOW)}
        r["count"] += 1
        r["total_ms"] += ms
        r["max_ms"] = max(r["max_ms"], ms)
        r["samples"].append(ms)
        if 400 <= status < 500:
            r["client_errors"] += 1
        elif status >= 500:
            r["server_errors"] += 1


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, max(0, round(p / 100 * (len(sorted_vals) - 1))))
    return round(sorted_vals[i], 2)


def snapshot() -> dict[str, Any]:
    with _lock:
        items = [(k, dict(v, samples=sorted(v["samples"]))) for k, v in _routes.items()]
    routes = []
    total = errors = 0
    for key, r in items:
        s = r["samples"]
        total += r["count"]
        errors += r["server_errors"]
        routes.append({
            "route": key,
            "count": r["count"],
            "client_errors": r["client_errors"],
            "server_errors": r["server_errors"],
            "avg_ms": round(r["total_ms"] / r["count"], 2),
            "p50_ms": _pct(s, 50),
            "p95_ms": _pct(s, 95),
            "p99_ms": _pct(s, 99),
            "max_ms": round(r["max_ms"], 2),
        })
    routes.sort(key=lambda x: x["count"] * x["avg_ms"], reverse=True)  # most total time first
    return {
        "uptime_s": round(time.time() - _started),
        "requests": total,
        "server_error_rate": round(errors / total, 4) if total else 0.0,
        "routes": routes,
    }
