"""Process-local runtime state shared by dashboard and trading components.

This module is intentionally state-only. It never starts an engine, performs
market I/O, or executes an order. It provides a safe read-only view of the
currently running process and the latest completed AI result.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any, Optional

_lock = RLock()
_engine_running = False
_engine_mode = "paper"
_engine_started_at: Optional[datetime] = None
_last_cycle_at: Optional[datetime] = None
_last_orchestrator_result: Any = None


def set_engine_running(running: bool, mode: str = "paper") -> None:
    global _engine_running, _engine_mode, _engine_started_at
    with _lock:
        _engine_running = bool(running)
        _engine_mode = str(mode or "paper").lower()
        _engine_started_at = datetime.now(timezone.utc) if _engine_running else None


def is_engine_running() -> bool:
    with _lock:
        return _engine_running


def get_engine_status() -> dict[str, Any]:
    with _lock:
        now = datetime.now(timezone.utc)
        runtime_seconds = 0.0
        if _engine_running and _engine_started_at:
            runtime_seconds = max(0.0, (now - _engine_started_at).total_seconds())
        return {
            "running": _engine_running,
            "mode": _engine_mode,
            "started_at": _engine_started_at.isoformat() if _engine_started_at else None,
            "runtime_seconds": runtime_seconds,
            "last_cycle_at": _last_cycle_at.isoformat() if _last_cycle_at else None,
        }


def record_cycle(timestamp: Optional[datetime] = None) -> None:
    global _last_cycle_at
    with _lock:
        _last_cycle_at = timestamp or datetime.now(timezone.utc)


def set_last_orchestrator_result(result: Any) -> None:
    global _last_orchestrator_result
    with _lock:
        _last_orchestrator_result = result
        timestamp = getattr(result, "timestamp", None)
        record_cycle(timestamp if isinstance(timestamp, datetime) else None)


def get_last_orchestrator_result() -> Any:
    with _lock:
        return _last_orchestrator_result
