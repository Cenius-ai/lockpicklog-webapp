"""T5 - the README's scripted example must work exactly as written.

This replays the sequence from the README, and checks that the failure example
quoted there is the error the CLI actually prints, word for word.
"""

from __future__ import annotations

import time

from helpers import REPO_ROOT, run_cli

README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

QUOTED_HEIGHT_ERROR = (
    "error: argument --height: height must be between 0 and 9 (got '12'); "
    "usage: lockpicklog pins add <lock_id> --position <1..n> --height <0-9> [--note <text>]"
)


def test_readme_quotes_a_real_error_verbatim(tmp_path):
    assert QUOTED_HEIGHT_ERROR in README, "the README no longer quotes this error"

    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)

    proc = run_cli("pins", "add", "1", "--position", "1", "--height", "12", data_path=data)

    assert proc.returncode == 2
    assert proc.stderr.strip() == QUOTED_HEIGHT_ERROR
    assert "no pins logged for lock 1" in run_cli("pins", "show", "1", data_path=data).stdout


def test_readme_scripted_sequence_runs_and_reports_50_percent(tmp_path):
    data = tmp_path / "data.json"

    steps = [
        ["locks", "add", "--model", "Master 140", "--method", "rake", "--note", "practice padlock"],
        ["pins", "add", "1", "--position", "1", "--height", "3"],
        ["pins", "add", "1", "--position", "2", "--height", "5"],
        ["practice", "start", "1"],
    ]
    for step in steps:
        assert run_cli(*step, data_path=data).returncode == 0, step

    time.sleep(1.1)
    assert run_cli("practice", "stop", "--success", data_path=data).returncode == 0

    assert run_cli("practice", "start", "1", data_path=data).returncode == 0
    time.sleep(1.1)
    assert run_cli("practice", "stop", "--failure", data_path=data).returncode == 0

    stats = run_cli("practice", "stats", data_path=data)
    assert stats.returncode == 0
    assert "sessions       2" in stats.stdout
    assert "opened         1" in stats.stdout
    assert "50% (1 of 2)" in stats.stdout


def test_readme_documents_the_store_path_the_override_and_every_command():
    for needle in (
        "$HOME/.lockpicklog/data.json",
        "LOCKPICKLOG_DATA",
        "Python 3.9",
        "locks add --model <text> --method <text> [--note <text>]",
        "locks list",
        "locks show <lock_id>",
        "pins add <lock_id> --position <1..n> --height <0-9> [--note <text>]",
        "pins show <lock_id>",
        "practice start [<lock_id>]",
        "practice stop --success",
        "practice stats [--lock <lock_id>]",
    ):
        assert needle in README, needle
