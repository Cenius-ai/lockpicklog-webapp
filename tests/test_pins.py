"""F2 - pin tumbler sequence notes."""

from __future__ import annotations

from helpers import lines, made_lock, read_store, run_cli, store_with, write_store


def stack_rows(output: str):
    """Data rows of a pin table: a leading integer, then the height."""
    rows = []
    for line in output.splitlines():
        cells = line.split()
        if len(cells) >= 2 and cells[0].isdigit():
            rows.append(cells)
    return rows


def test_add_then_show_one_pin(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)

    added = run_cli("pins", "add", "1", "--position", "1", "--height", "3", data_path=data)
    assert added.returncode == 0
    assert "position 1" in added.stdout

    shown = run_cli("pins", "show", "1", data_path=data)
    assert shown.returncode == 0
    rows = stack_rows(shown.stdout)
    assert rows == [["1", "3"]]


def test_out_of_range_heights_are_rejected_and_change_nothing(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("pins", "add", "1", "--position", "1", "--height", "3", data_path=data)
    before = data.read_text(encoding="utf-8")

    for bad_height in ("12", "-1", "abc"):
        proc = run_cli("pins", "add", "1", "--position", "2", "--height", bad_height, data_path=data)
        assert proc.returncode == 2
        assert proc.stdout == ""
        stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
        assert len(stderr_lines) == 1
        assert "height" in stderr_lines[0]
        assert bad_height in stderr_lines[0]
        assert "usage: lockpicklog pins add" in stderr_lines[0]
        assert data.read_text(encoding="utf-8") == before


def test_non_integer_position_is_rejected(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    before = data.read_text(encoding="utf-8")

    proc = run_cli("pins", "add", "1", "--position", "abc", "--height", "3", data_path=data)
    assert proc.returncode == 2
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "position must be a whole number" in stderr_lines[0]
    assert data.read_text(encoding="utf-8") == before


def test_negative_position_is_rejected(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)

    proc = run_cli("pins", "add", "1", "--position", "-2", "--height", "3", data_path=data)
    assert proc.returncode == 2
    assert "position" in proc.stderr
    assert read_store(data)["pins"] == []


def test_unknown_lock_id_stores_nothing(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)

    proc = run_cli("pins", "add", "9999", "--position", "1", "--height", "3", data_path=data)
    assert proc.returncode == 2
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "9999" in stderr_lines[0]

    document = read_store(data)
    assert len(document["locks"]) == 1
    assert document["pins"] == []

    # `pins show` on an unknown lock reports the error rather than a pin list.
    shown = run_cli("pins", "show", "9999", data_path=data)
    assert shown.returncode == 2
    assert shown.stdout == ""
    assert "9999" in shown.stderr


def test_pins_are_shown_in_ascending_position_order(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("pins", "add", "1", "--position", "3", "--height", "5", data_path=data)
    run_cli("pins", "add", "1", "--position", "1", "--height", "3", data_path=data)

    shown = run_cli("pins", "show", "1", data_path=data)
    assert [row[0] for row in stack_rows(shown.stdout)] == ["1", "3"]


def test_re_logging_a_position_updates_it_instead_of_duplicating(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("pins", "add", "1", "--position", "2", "--height", "5", data_path=data)

    updated = run_cli("pins", "add", "1", "--position", "2", "--height", "7", data_path=data)
    assert updated.returncode == 0
    assert "updated position 2" in updated.stdout

    rows = stack_rows(run_cli("pins", "show", "1", data_path=data).stdout)
    assert rows == [["2", "7"]]

    pins = read_store(data)["pins"]
    assert len(pins) == 1
    assert pins[0]["height"] == 7


def test_pin_note_is_shown_on_the_same_line(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)
    run_cli("pins", "add", "1", "--position", "2", "--height", "4", "--note", "spool", data_path=data)

    shown = run_cli("pins", "show", "1", data_path=data)
    row = [line for line in shown.stdout.splitlines() if line.strip().startswith("2 ")]
    assert len(row) == 1
    assert "4" in row[0]
    assert "spool" in row[0]


def test_empty_stack_invites_the_first_pin(tmp_path):
    data = tmp_path / "data.json"
    run_cli("locks", "add", "--model", "Master 140", "--method", "rake", data_path=data)

    shown = run_cli("pins", "show", "1", data_path=data)
    assert shown.returncode == 0
    assert (
        "no pins logged for lock 1 - add one with: lockpicklog pins add 1 --position <n> --height <h>"
        in shown.stdout
    )


def test_update_keeps_an_existing_note_when_note_is_omitted(tmp_path):
    data = write_store(
        tmp_path / "data.json",
        store_with(
            locks=[made_lock(1)],
            pins=[
                {
                    "id": 1,
                    "lock_id": 1,
                    "position": 1,
                    "height": 3,
                    "note": "low cut",
                    "created_at": "2026-01-01T10:00:00+00:00",
                }
            ],
        ),
    )
    run_cli("pins", "add", "1", "--position", "1", "--height", "6", data_path=data)

    pin = read_store(data)["pins"][0]
    assert pin["height"] == 6
    assert pin["note"] == "low cut"
