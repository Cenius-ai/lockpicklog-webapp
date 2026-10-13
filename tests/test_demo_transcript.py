"""T5 - the committed transcript must be a faithful capture, not a mockup.

The walkthrough is replayed through `demo.sh` and compared, line for line, with
demo/session.txt. Only the two genuinely clock-derived tokens are masked: the
absolute UTC timestamps and the elapsed-second figures, because neither can be
identical across two runs of a real timer.
"""

from __future__ import annotations

import difflib
import os
import re
import subprocess

from helpers import REPO_ROOT

TRANSCRIPT = REPO_ROOT / "demo" / "session.txt"

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+00:00)?")
_AGE = re.compile(r"\((?:just now|\d+ (?:min|h|d) ago)\)")
_STOP_DURATION = re.compile(r"(complete: (?:opened|not opened) in )\S+( for )")
_AVG_OPEN = re.compile(r"^(  avg open time  )\S+$", re.MULTILINE)


def mask(text: str) -> str:
    text = _TIMESTAMP.sub("<timestamp>", text)
    text = _AGE.sub("(<age>)", text)
    text = _STOP_DURATION.sub(r"\1<duration>\2", text)
    text = _AVG_OPEN.sub(r"\1<duration>", text)
    return text


def test_demo_transcript_replays_line_for_line(tmp_path):
    recorded = mask(TRANSCRIPT.read_text(encoding="utf-8"))

    environ = dict(os.environ)
    environ["PYTHON"] = "python3"
    environ["HOME"] = str(tmp_path)  # never touch the real user's log
    proc = subprocess.run(
        ["bash", "demo.sh"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(REPO_ROOT),
        env=environ,
        timeout=300,
    )
    live = mask(proc.stdout)

    assert proc.returncode == 0
    if live != recorded:
        diff = "\n".join(
            difflib.unified_diff(
                recorded.splitlines(), live.splitlines(), "demo/session.txt", "live run", lineterm=""
            )
        )
        raise AssertionError("transcript drifted from a live run:\n" + diff)


def test_demo_leaves_no_store_behind():
    assert not (REPO_ROOT / ".demo-store").exists()
