"""Shared helpers for the LockpickLog test suite.

Every test drives the real CLI as a separate process, because "the log must
survive between runs" is the whole point of the tool: an in-process call would
not prove it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "lockpicklog.py"


def run_cli(*args: Any, data_path: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run `python3 lockpicklog.py <args>` against an isolated store."""
    environ = dict(os.environ)
    environ["LOCKPICKLOG_DATA"] = str(data_path)
    environ["NO_COLOR"] = "1"
    environ.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, str(TOOL)] + [str(arg) for arg in args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=environ,
        timeout=timeout,
    )


def read_store(data_path: Path) -> Dict[str, Any]:
    return json.loads(Path(data_path).read_text(encoding="utf-8"))


def lines(proc: subprocess.CompletedProcess) -> List[str]:
    return [line for line in proc.stdout.splitlines() if line.strip()]


def store_with(
    locks: Sequence[Dict[str, Any]] = (),
    pins: Sequence[Dict[str, Any]] = (),
    sessions: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    """Build a store document the way the CLI writes it (for fixture stores)."""
    locks = list(locks)
    pins = list(pins)
    sessions = list(sessions)
    return {
        "schema_version": 1,
        "locks": locks,
        "pins": pins,
        "sessions": sessions,
        "next_ids": {
            "locks": 1 + max((item["id"] for item in locks), default=0),
            "pins": 1 + max((item["id"] for item in pins), default=0),
            "sessions": 1 + max((item["id"] for item in sessions), default=0),
        },
    }


def write_store(data_path: Path, document: Dict[str, Any]) -> Path:
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def made_lock(lock_id: int, model: str = "Master 140", method: str = "rake", note: str = "") -> Dict[str, Any]:
    return {
        "id": lock_id,
        "model": model,
        "method": method,
        "note": note,
        "created_at": "2026-01-01T10:00:00+00:00",
    }


def made_session(
    session_id: int,
    lock_id: Any = None,
    duration: int = 10,
    success: bool = True,
    started_at: str = "2026-01-01T10:00:00+00:00",
) -> Dict[str, Any]:
    return {
        "id": session_id,
        "lock_id": lock_id,
        "started_at": started_at,
        "started_monotonic": 1000.0 + session_id,
        "ended_at": started_at,
        "duration_seconds": duration,
        "success": success,
    }
