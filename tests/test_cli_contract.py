"""F5 - the CLI contract: help, streams, exit codes, colour behaviour."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from helpers import REPO_ROOT, TOOL, run_cli

SUBCOMMANDS = [
    ["locks", "--help"],
    ["locks", "add", "--help"],
    ["locks", "list", "--help"],
    ["locks", "show", "--help"],
    ["pins", "--help"],
    ["pins", "add", "--help"],
    ["pins", "show", "--help"],
    ["practice", "--help"],
    ["practice", "start", "--help"],
    ["practice", "stop", "--help"],
    ["practice", "stats", "--help"],
]


def test_help_lists_every_command_and_example(tmp_path):
    proc = run_cli("--help", data_path=tmp_path / "data.json")

    assert proc.returncode == 0
    for word in ("locks", "pins", "practice", "examples:", "LOCKPICKLOG_DATA", "exit codes:"):
        assert word in proc.stdout
    assert "lockpicklog locks add --model" in proc.stdout


def test_every_subcommand_has_help(tmp_path):
    for args in SUBCOMMANDS:
        proc = run_cli(*args, data_path=tmp_path / "data.json")
        assert proc.returncode == 0, args
        assert "usage: lockpicklog" in proc.stdout, args


def test_version_flag(tmp_path):
    proc = run_cli("--version", data_path=tmp_path / "data.json")
    assert proc.returncode == 0
    assert "LockpickLog" in proc.stdout


def test_bare_invocation_is_help_first_and_exits_zero(tmp_path):
    proc = run_cli(data_path=tmp_path / "data.json")
    assert proc.returncode == 0
    assert "usage: lockpicklog" in proc.stdout


def test_group_without_an_action_prints_that_group_help(tmp_path):
    proc = run_cli("pins", data_path=tmp_path / "data.json")
    assert proc.returncode == 0
    assert "usage: lockpicklog pins" in proc.stdout


def test_unknown_command_is_a_one_line_error(tmp_path):
    proc = run_cli("pick", data_path=tmp_path / "data.json")
    assert proc.returncode == 2
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "usage:" in stderr_lines[0]


def test_records_go_to_stdout_and_errors_to_stderr(tmp_path):
    data = tmp_path / "data.json"
    ok = run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    assert ok.stdout.strip() != ""
    assert ok.stderr == ""

    bad = run_cli("locks", "show", "42", data_path=data)
    assert bad.stdout == ""
    assert bad.stderr.strip() != ""


def test_no_ansi_escapes_when_output_is_not_a_terminal(tmp_path):
    env = dict(os.environ)
    env["LOCKPICKLOG_DATA"] = str(tmp_path / "data.json")
    env.pop("NO_COLOR", None)
    proc = subprocess.run(
        [sys.executable, str(TOOL), "locks", "list"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert proc.returncode == 0
    assert "\033[" not in proc.stdout


def test_exit_code_contract(tmp_path):
    data = tmp_path / "data.json"
    assert run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data).returncode == 0
    assert run_cli("pins", "add", "1", "--position", "0", "--height", "3", data_path=data).returncode == 2
    assert run_cli("locks", "show", "7", data_path=data).returncode == 2

    broken = tmp_path / "broken.json"
    broken.write_text("nope", encoding="utf-8")
    assert run_cli("locks", "list", data_path=broken).returncode == 1


def test_runs_with_a_bare_environment_and_no_configuration(tmp_path):
    """No LOCKPICKLOG_DATA, no NO_COLOR, an untouched HOME: it still boots."""
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TERM") if key in os.environ}
    env["HOME"] = str(tmp_path)

    proc = subprocess.run(
        [sys.executable, str(TOOL), "locks", "add", "--model", "Master 140", "--method", "rake"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    assert proc.returncode == 0
    assert "added lock 1" in proc.stdout
    created = tmp_path / ".lockpicklog" / "data.json"
    assert created.exists()
    assert json.loads(created.read_text(encoding="utf-8"))["schema_version"] == 1
