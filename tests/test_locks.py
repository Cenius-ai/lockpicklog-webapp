"""F1 - log a lock's model and picking method."""

from __future__ import annotations

from helpers import lines, read_store, run_cli


def test_add_prints_the_new_id_and_list_shows_the_lock(tmp_path):
    data = tmp_path / "data.json"
    added = run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    assert added.returncode == 0
    assert "added lock 1" in added.stdout

    listed = run_cli("locks", "list", data_path=data)
    assert listed.returncode == 0
    row = [line for line in lines(listed) if "Master 140" in line]
    assert len(row) == 1
    assert "rake" in row[0]


def test_optional_note_is_stored_and_shown(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    added = run_cli("locks", "add", "--model", "ABUS 55/40", "--method", "spp", "--note", "worn pins", data_path=data)
    assert added.returncode == 0

    listed = run_cli("locks", "list", data_path=data)
    assert "worn pins" in listed.stdout
    assert read_store(data)["locks"][1]["note"] == "worn pins"


def test_list_is_newest_first(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Lock A", "--method", "rake", data_path=data)
    run_cli("locks", "add", "--model", "Lock B", "--method", "spp", data_path=data)

    rows = [line for line in lines(run_cli("locks", "list", data_path=data)) if "Lock " in line]
    assert len(rows) == 2
    assert "Lock B" in rows[0]
    assert "Lock A" in rows[1]


def test_show_prints_every_stored_field(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", "--note", "cheap padlock", data_path=data)

    shown = run_cli("locks", "show", "1", data_path=data)
    assert shown.returncode == 0
    for expected in ("Master 140", "rake", "cheap padlock", "1"):
        assert expected in shown.stdout


def test_show_with_unknown_id_is_a_one_line_error_and_writes_nothing(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    before = data.read_text(encoding="utf-8")

    proc = run_cli("locks", "show", "99", data_path=data)
    assert proc.returncode == 2
    assert proc.stdout == ""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "99" in stderr_lines[0]
    assert "usage:" in stderr_lines[0]
    assert data.read_text(encoding="utf-8") == before


def test_blank_model_is_rejected_and_stores_nothing(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    before = data.read_text(encoding="utf-8")

    proc = run_cli("locks", "add", "--model", "", "--method", "rake", data_path=data)
    assert proc.returncode == 2
    assert proc.stdout == ""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "--model" in stderr_lines[0]
    assert "locks add --model <text> --method <text>" in stderr_lines[0]

    assert data.read_text(encoding="utf-8") == before
    assert len(read_store(data)["locks"]) == 1


def test_missing_method_flag_is_rejected(tmp_path):
    data = tmp_path / "data.json"
    proc = run_cli("locks", "add", "--model", "Master 140", data_path=data)

    assert proc.returncode == 2
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "--method" in stderr_lines[0]
    assert "usage:" in stderr_lines[0]
    assert not data.exists()


def test_blank_method_is_rejected(tmp_path):
    data = tmp_path / "data.json"
    proc = run_cli("locks", "add", "--model", "Master 140", "--method", "   ", data_path=data)

    assert proc.returncode == 2
    assert "--method" in proc.stderr
    assert not data.exists()


def test_empty_state_invites_the_first_lock_and_exits_zero(tmp_path):
    data = tmp_path / "data.json"
    proc = run_cli("locks", "list", data_path=data)

    assert proc.returncode == 0
    assert (
        "no locks logged yet - add one with: lockpicklog locks add --model <text> --method <text>"
        in proc.stdout
    )
