"""F3 - practice timer and success-rate stats."""

from __future__ import annotations

import time

from helpers import made_lock, made_session, read_store, run_cli, store_with, write_store


def test_start_then_stop_across_processes_records_the_elapsed_time(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)

    started = run_cli("practice", "start", "1", data_path=data)
    assert started.returncode == 0
    assert "timer running" in started.stdout

    time.sleep(1.2)
    stopped = run_cli("practice", "stop", "--success", data_path=data)
    assert stopped.returncode == 0
    assert "opened" in stopped.stdout
    assert "for lock 1 - Master 140" in stopped.stdout

    session = read_store(data)["sessions"][0]
    assert session["started_at"]
    assert isinstance(session["started_monotonic"], float)
    assert session["ended_at"]
    assert 1 <= session["duration_seconds"] <= 5
    assert session["success"] is True


def test_unattributed_session_is_allowed_and_labelled(tmp_path):
    data = tmp_path / "data.json"
    assert run_cli("practice", "start", data_path=data).returncode == 0
    stopped = run_cli("practice", "stop", "--failure", data_path=data)

    assert stopped.returncode == 0
    assert "unattributed" in stopped.stdout
    assert read_store(data)["sessions"][0]["lock_id"] is None


def test_stop_with_no_timer_is_a_one_line_error_and_writes_nothing(tmp_path):
    data = tmp_path / "data.json"

    proc = run_cli("practice", "stop", "--success", data_path=data)
    assert proc.returncode == 2
    assert proc.stdout == ""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "no timer is running" in stderr_lines[0]
    assert "usage: lockpicklog practice stop --success|--failure" in stderr_lines[0]
    # first use creates the empty log file; not a single session is recorded
    assert read_store(data)["sessions"] == []


def test_a_second_timer_is_refused_while_one_is_running(tmp_path):
    data = tmp_path / "data.json"
    run_cli("practice", "start", data_path=data)
    before = data.read_text(encoding="utf-8")

    proc = run_cli("practice", "start", data_path=data)
    assert proc.returncode == 2
    assert "already running" in proc.stderr
    assert data.read_text(encoding="utf-8") == before


def test_start_with_unknown_lock_id_records_nothing(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    before = data.read_text(encoding="utf-8")

    proc = run_cli("practice", "start", "9999", data_path=data)
    assert proc.returncode == 2
    assert "9999" in proc.stderr
    assert data.read_text(encoding="utf-8") == before

    stats = run_cli("practice", "stats", data_path=data)
    assert "no sessions recorded yet" in stats.stdout


def test_stats_is_empty_friendly_and_exits_zero(tmp_path):
    data = tmp_path / "data.json"
    proc = run_cli("practice", "stats", data_path=data)

    assert proc.returncode == 0
    assert "no sessions recorded yet - start a timer with: lockpicklog practice start [<lock_id>]" in proc.stdout
    assert "%" not in proc.stdout


def test_stats_math_over_three_sessions(tmp_path):
    """10s opened, 20s opened, 40s failed -> 3 sessions, 67%, 15s average."""
    data = write_store(
        tmp_path / "data.json",
        store_with(
            locks=[made_lock(1)],
            sessions=[
                made_session(1, lock_id=1, duration=10, success=True),
                made_session(2, lock_id=1, duration=20, success=True),
                made_session(3, lock_id=1, duration=40, success=False),
            ],
        ),
    )
    proc = run_cli("practice", "stats", data_path=data)

    assert proc.returncode == 0
    assert "sessions       3" in proc.stdout
    assert "opened         2" in proc.stdout
    assert "67% (2 of 3)" in proc.stdout
    assert "avg open time  15s" in proc.stdout


def test_failure_outcome_counts_but_is_not_an_open(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("practice", "start", "1", data_path=data)
    time.sleep(1.1)
    run_cli("practice", "stop", "--failure", data_path=data)

    assert read_store(data)["sessions"][0]["success"] is False

    stats = run_cli("practice", "stats", data_path=data)
    assert "sessions       1" in stats.stdout
    assert "opened         0" in stats.stdout
    assert "0% (0 of 1)" in stats.stdout
    assert "n/a" in stats.stdout


def test_stats_lock_filter_ignores_other_locks(tmp_path):
    data = write_store(
        tmp_path / "data.json",
        store_with(
            locks=[made_lock(1, "Master 140"), made_lock(2, "ABUS 55/40", "spp")],
            sessions=[
                made_session(1, lock_id=1, duration=10, success=True),
                made_session(2, lock_id=2, duration=40, success=False),
                made_session(3, lock_id=2, duration=50, success=True),
            ],
        ),
    )
    proc = run_cli("practice", "stats", "--lock", "1", data_path=data)

    assert proc.returncode == 0
    assert "lock 1 - Master 140" in proc.stdout
    assert "sessions       1" in proc.stdout
    assert "opened         1" in proc.stdout
    assert "100% (1 of 1)" in proc.stdout
    assert "avg open time  10s" in proc.stdout


def test_stats_with_unknown_lock_is_refused(tmp_path):
    data = tmp_path / "data.json"
    proc = run_cli("practice", "stats", "--lock", "9999", data_path=data)

    assert proc.returncode == 2
    assert "9999" in proc.stderr
    assert "usage: lockpicklog practice stats" in proc.stderr


def test_stats_for_a_lock_with_no_completed_sessions(tmp_path):
    data = write_store(tmp_path / "data.json", store_with(locks=[made_lock(1)]))

    proc = run_cli("practice", "stats", "--lock", "1", data_path=data)
    assert proc.returncode == 0
    assert "no completed sessions for lock 1 yet" in proc.stdout


def test_a_running_session_is_excluded_from_stats_until_it_is_stopped(tmp_path):
    data = tmp_path / "data.json"
    run_cli("practice", "start", data_path=data)

    stats = run_cli("practice", "stats", data_path=data)
    assert stats.returncode == 0
    assert "no sessions recorded yet" in stats.stdout
