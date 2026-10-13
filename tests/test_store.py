"""F4 - the local on-disk log: creation, process boundaries, atomic writes."""

from __future__ import annotations

import json
import time

from helpers import read_store, run_cli


def test_first_use_creates_the_store_with_schema_version_and_empty_lists(tmp_path):
    data = tmp_path / "nested" / "data.json"
    proc = run_cli("locks", "list", data_path=data)

    assert proc.returncode == 0
    assert "no locks logged yet" in proc.stdout

    document = read_store(data)
    assert document["schema_version"] == 1
    assert document["locks"] == []
    assert document["pins"] == []
    assert document["sessions"] == []


def test_records_survive_a_separate_process(tmp_path):
    data = tmp_path / "data.json"
    assert run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data).returncode == 0

    later = run_cli("locks", "list", data_path=data)
    assert later.returncode == 0
    assert "Master 140" in later.stdout


def test_in_progress_session_round_trips_as_json_with_nulls(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("practice", "start", "1", data_path=data)

    # Read the raw file: the running-timer marker must be durable on disk.
    raw = json.loads(data.read_text(encoding="utf-8"))
    session = raw["sessions"][0]
    assert session["lock_id"] == 1
    assert isinstance(session["started_monotonic"], float)
    assert isinstance(session["started_at"], str) and session["started_at"]
    assert session["ended_at"] is None
    assert session["duration_seconds"] is None
    assert session["success"] is None

    time.sleep(1.2)
    stop = run_cli("practice", "stop", "--success", data_path=data)
    assert stop.returncode == 0

    finished = read_store(data)["sessions"][0]
    assert finished["id"] == session["id"]
    assert finished["duration_seconds"] >= 1
    assert finished["success"] is True
    assert finished["ended_at"] is not None


def test_invalid_json_exits_one_and_leaves_the_file_untouched(tmp_path):
    data = tmp_path / "data.json"
    broken = "{ this is not json"
    data.write_text(broken, encoding="utf-8")

    proc = run_cli("locks", "list", data_path=data)

    assert proc.returncode == 1
    assert proc.stdout == ""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "data.json" in stderr_lines[0]
    assert "not valid JSON" in stderr_lines[0]
    assert data.read_text(encoding="utf-8") == broken


def test_writes_leave_no_temporary_file_behind(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("locks", "add", "--model", "ABUS 55/40", "--method", "spp", data_path=data)
    run_cli("pins", "add", "1", "--position", "1", "--height", "3", data_path=data)

    leftovers = [entry.name for entry in tmp_path.iterdir() if entry.name != "data.json"]
    assert leftovers == []
    # ... and the store is complete and readable, never half-written.
    assert len(read_store(data)["locks"]) == 2


def test_unsupported_schema_version_is_a_storage_error(tmp_path):
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"schema_version": 99, "locks": [], "pins": [], "sessions": []}), encoding="utf-8")

    proc = run_cli("locks", "list", data_path=data)
    assert proc.returncode == 1
    assert "schema_version" in proc.stderr
