#!/usr/bin/env python3
"""LockpickLog - a local practice log for locks, pin stacks and timed picks.

Single file, Python 3.9+, standard library only, no network access.
The whole log lives in one human-readable JSON file that is written
atomically, so the log always survives between separate invocations.

    python3 lockpicklog.py locks add --model "Master 140" --method rake
    python3 lockpicklog.py pins add 1 --position 1 --height 3 --note "low cut"
    python3 lockpicklog.py practice start 1
    python3 lockpicklog.py practice stop --success
    python3 lockpicklog.py practice stats
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, NoReturn, Optional, Sequence, Tuple

SCHEMA_VERSION = 1
PROG = "lockpicklog"
AUTHOR = "LockpickLog"
VERSION = "1.0.0"

EXIT_OK = 0
EXIT_STORAGE = 1
EXIT_USAGE = 2

# --------------------------------------------------------------------------
# Design tokens (committed direction: calm-precise, terminal dark)
#
#   accent   : oklch(0.58 0.12 43) == #b4603c - one accent, used for primary
#              status values and the box-drawing rules. Colour is never the
#              only signal: every accent-coloured value also carries a word.
#   surface  : terminal dark, monospace, no chrome
#   shape    : aligned columns, box-drawing separators, one rule style
# --------------------------------------------------------------------------

ACCENT_OKLCH = "oklch(0.58 0.12 43)"
ACCENT_HEX = "#b4603c"
ACCENT_RGB = (180, 96, 60)

RULE_CHAR = "\u2500"  # box drawing light horizontal

_COLOUR_ON = False


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class StorageError(Exception):
    """Storage / IO failure: exit 1. The store is never modified."""


class UsageError(Exception):
    """Bad input from the user: exit 2. Nothing is ever written."""

    def __init__(self, message: str, usage: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.usage = usage


# --------------------------------------------------------------------------
# Palette and output helpers
# --------------------------------------------------------------------------


def _wants_colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    stream = sys.stdout
    return bool(getattr(stream, "isatty", None) and stream.isatty())


def use_colour(enabled: bool) -> None:
    global _COLOUR_ON
    _COLOUR_ON = bool(enabled)


def accent(text: str) -> str:
    """Colour a string with the one committed accent (a no-op when not a TTY)."""
    if not _COLOUR_ON:
        return text
    red, green, blue = ACCENT_RGB
    return "\033[38;2;{};{};{}m{}\033[0m".format(red, green, blue, text)


def emit(line: str = "") -> None:
    print(line.rstrip())


def fail(message: str, usage: str = "") -> NoReturn:
    raise UsageError(message, usage)


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(text: str) -> Optional[datetime]:
    try:
        stamp = datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def humanise(stamp_text: str) -> str:
    """Turn a stored ISO timestamp into a short readable phrase."""
    stamp = parse_iso(stamp_text)
    if stamp is None:
        return str(stamp_text)
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    if age < 0:
        age = 0.0
    if age < 60:
        return "just now"
    if age < 3600:
        return "{:.0f} min ago".format(age / 60)
    if age < 86400:
        return "{:.0f} h ago".format(age / 3600)
    if age < 86400 * 7:
        return "{:.0f} d ago".format(age / 86400)
    return stamp.strftime("%Y-%m-%d")


def humanise_duration(seconds: int) -> str:
    if seconds < 60:
        return "{}s".format(seconds)
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return "{}m {:02d}s".format(minutes, rest)
    hours, minutes = divmod(minutes, 60)
    return "{}h {:02d}m".format(hours, minutes)


# --------------------------------------------------------------------------
# Rendering: aligned columns with one box-drawing rule style
# --------------------------------------------------------------------------


def render_rule(width: int) -> str:
    return accent(RULE_CHAR * max(8, width))


def title_block(title: str) -> None:
    emit(accent(title))
    emit(render_rule(len(title)))


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]], numeric: Sequence[int] = ()) -> None:
    """Print an aligned table; the numeric columns are right-aligned."""
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def pad(cell: str, index: int) -> str:
        if index in numeric:
            return cell.rjust(widths[index])
        return cell.ljust(widths[index])

    emit("  " + "  ".join(pad(header, index) for index, header in enumerate(headers)))
    emit("  " + "  ".join(accent(RULE_CHAR * width) for width in widths))
    for row in rows:
        emit("  " + "  ".join(pad(cell, index) for index, cell in enumerate(row)))


def render_fields(pairs: Sequence[Tuple[str, str]], accent_keys: Sequence[str] = ()) -> None:
    """Print aligned 'label  value' lines, accenting the value of named labels."""
    width = max((len(label) for label, _ in pairs), default=0)
    for label, value in pairs:
        shown = accent(value) if label in accent_keys else value
        emit("  " + label.ljust(width) + "  " + shown)


# --------------------------------------------------------------------------
# Store: one JSON file, atomic writes
# --------------------------------------------------------------------------


def store_path() -> Path:
    override = os.environ.get("LOCKPICKLOG_DATA", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".lockpicklog" / "data.json"


def empty_store() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "locks": [],
        "pins": [],
        "sessions": [],
        "next_ids": {"locks": 1, "pins": 1, "sessions": 1},
    }


def _next_id_from(records: Sequence[Dict[str, Any]]) -> int:
    return 1 + max((int(record.get("id", 0)) for record in records), default=0)


def load_store(path: Path) -> Dict[str, Any]:
    """Read the store. A missing file yields a fresh empty store."""
    if not path.exists():
        store = empty_store()
        save_store(path, store)  # first use: the log file is created for you
        return store
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StorageError("cannot read store {}: {}".format(path, exc.strerror or exc))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StorageError(
            "store {} is not valid JSON (line {}, column {}); fix or remove the file".format(
                path, exc.lineno, exc.colno
            )
        )

    if not isinstance(data, dict):
        raise StorageError("store {} is not a JSON object; remove it to start fresh".format(path))

    for key in ("locks", "pins", "sessions"):
        if not isinstance(data.get(key), list):
            raise StorageError(
                "store {} is missing the '{}' list; remove it to start fresh".format(path, key)
            )

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise StorageError(
            "store {} has unsupported schema_version {} (this build reads {})".format(
                path, version, SCHEMA_VERSION
            )
        )

    counters = data.get("next_ids")
    if not isinstance(counters, dict):
        counters = {}
    for key in ("locks", "pins", "sessions"):
        stored = counters.get(key, 1)
        try:
            stored = int(stored)
        except (TypeError, ValueError):
            stored = 1
        counters[key] = max(stored, _next_id_from(data[key]))
    data["next_ids"] = counters
    data["schema_version"] = version
    return data


def save_store(path: Path, store: Dict[str, Any]) -> None:
    """Write the store atomically: temp file in the same directory, then os.replace."""
    payload = json.dumps(store, indent=2) + "\n"
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise StorageError("cannot create store directory {}: {}".format(parent, exc.strerror or exc))

    tmp_name: Optional[str] = None
    try:
        handle_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(parent))
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, str(path))
    except OSError as exc:
        if tmp_name:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
        raise StorageError("cannot write store {}: {}".format(path, exc.strerror or exc))


def allocate_id(store: Dict[str, Any], kind: str) -> int:
    counters = store["next_ids"]
    new_id = max(int(counters.get(kind, 1)), _next_id_from(store[kind]))
    counters[kind] = new_id + 1
    return new_id


# --------------------------------------------------------------------------
# Domain helpers
# --------------------------------------------------------------------------


def find_lock(store: Dict[str, Any], lock_id: int) -> Optional[Dict[str, Any]]:
    for lock in store["locks"]:
        if int(lock.get("id", -1)) == lock_id:
            return lock
    return None


def require_lock(store: Dict[str, Any], lock_id: int, usage: str) -> Dict[str, Any]:
    lock = find_lock(store, lock_id)
    if lock is None:
        fail(
            "no lock with id {} exists ({} locks list shows the ids you have)".format(lock_id, PROG),
            usage,
        )
    return lock  # type: ignore[return-value]


def lock_label(lock: Optional[Dict[str, Any]]) -> str:
    if lock is None:
        return "unattributed"
    return "lock {0} - {1}".format(lock["id"], lock["model"])


def pins_for(store: Dict[str, Any], lock_id: int) -> List[Dict[str, Any]]:
    return sorted(
        (pin for pin in store["pins"] if int(pin.get("lock_id", -1)) == lock_id),
        key=lambda pin: int(pin.get("position", 0)),
    )


def running_session(store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The in-progress timer is the row with no duration and no outcome yet."""
    for session in reversed(store["sessions"]):
        if session.get("duration_seconds") is None and session.get("success") is None:
            return session
    return None


# --------------------------------------------------------------------------
# Usage forms (also printed in one-line errors)
# --------------------------------------------------------------------------

USAGE = {
    "root": "{0} <command> [options]   (see {0} --help)".format(PROG),
    "locks": "{0} locks <add|list|show>".format(PROG),
    "pins": "{0} pins <add|show>".format(PROG),
    "practice": "{0} practice <start|stop|stats>".format(PROG),
    "locks add": "{0} locks add --model <text> --method <text> [--note <text>]".format(PROG),
    "locks list": "{0} locks list".format(PROG),
    "locks show": "{0} locks show <lock_id>".format(PROG),
    "pins add": "{0} pins add <lock_id> --position <1..n> --height <0-9> [--note <text>]".format(PROG),
    "pins show": "{0} pins show <lock_id>".format(PROG),
    "practice start": "{0} practice start [<lock_id>]".format(PROG),
    "practice stop": "{0} practice stop --success|--failure".format(PROG),
    "practice stats": "{0} practice stats [--lock <lock_id>]".format(PROG),
}


# --------------------------------------------------------------------------
# Commands: locks
# --------------------------------------------------------------------------


def cmd_locks_add(args: argparse.Namespace) -> int:
    usage = USAGE["locks add"]
    model = (args.model or "").strip()
    method = (args.method or "").strip()
    if not model:
        fail("--model is required and must not be blank", usage)
    if not method:
        fail("--method is required and must not be blank", usage)

    path = store_path()
    store = load_store(path)
    lock = {
        "id": allocate_id(store, "locks"),
        "model": model,
        "method": method,
        "note": (args.note or "").strip(),
        "created_at": utc_now_iso(),
    }
    store["locks"].append(lock)
    save_store(path, store)

    emit("added lock {} - {} ({})".format(accent(str(lock["id"])), lock["model"], lock["method"]))
    return EXIT_OK


def cmd_locks_list(args: argparse.Namespace) -> int:
    path = store_path()
    store = load_store(path)
    locks = sorted(store["locks"], key=lambda lock: int(lock.get("id", 0)), reverse=True)

    if not locks:
        emit("no locks logged yet - add one with: {0} locks add --model <text> --method <text>".format(PROG))
        return EXIT_OK

    rows = []
    for lock in locks:
        pin_count = len(pins_for(store, int(lock["id"])))
        rows.append(
            [
                str(lock["id"]),
                str(lock.get("model", "")),
                str(lock.get("method", "")),
                str(lock.get("note", "")),
                "{} pin".format(pin_count) if pin_count == 1 else "{} pins".format(pin_count),
            ]
        )
    render_table(["ID", "MODEL", "METHOD", "NOTE", "PINS"], rows, numeric=(0, 4))
    return EXIT_OK


def cmd_locks_show(args: argparse.Namespace) -> int:
    path = store_path()
    store = load_store(path)
    lock = require_lock(store, args.lock_id, USAGE["locks show"])

    title_block("lock {}".format(lock["id"]))
    created = str(lock.get("created_at", ""))
    note = str(lock.get("note", ""))
    session_count = sum(1 for s in store["sessions"] if s.get("lock_id") == lock["id"])
    render_fields(
        [
            ("model", str(lock.get("model", ""))),
            ("method", str(lock.get("method", ""))),
            ("note", note if note else "(none)"),
            ("pins", "{} logged".format(len(pins_for(store, int(lock["id"]))))),
            ("sessions", "{} recorded".format(session_count)),
            ("created", "{} ({})".format(created, humanise(created))),
        ],
        accent_keys=("method",),
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# Commands: pins
# --------------------------------------------------------------------------


def cmd_pins_add(args: argparse.Namespace) -> int:
    usage = USAGE["pins add"]
    path = store_path()
    store = load_store(path)
    require_lock(store, args.lock_id, usage)

    note_given = args.note is not None
    note = (args.note or "").strip()
    existing: Optional[Dict[str, Any]] = None
    for pin in store["pins"]:
        if int(pin.get("lock_id", -1)) == args.lock_id and int(pin.get("position", -1)) == args.position:
            existing = pin
            break

    if existing is None:
        pin = {
            "id": allocate_id(store, "pins"),
            "lock_id": args.lock_id,
            "position": args.position,
            "height": args.height,
            "note": note,
            "created_at": utc_now_iso(),
        }
        store["pins"].append(pin)
        save_store(path, store)
        emit(
            "added pin at position {0} with height {1} for lock {2} (pin id {3})".format(
                accent(str(args.position)), args.height, args.lock_id, pin["id"]
            )
        )
        return EXIT_OK

    existing["height"] = args.height
    if note_given:
        existing["note"] = note
    existing["updated_at"] = utc_now_iso()
    save_store(path, store)
    emit(
        "updated position {0} for lock {1} - height is now {2} (no duplicate created)".format(
            accent(str(args.position)), args.lock_id, args.height
        )
    )
    return EXIT_OK


def cmd_pins_show(args: argparse.Namespace) -> int:
    path = store_path()
    store = load_store(path)
    lock = require_lock(store, args.lock_id, USAGE["pins show"])

    pins = pins_for(store, args.lock_id)
    if not pins:
        emit(
            "no pins logged for lock {0} - add one with: {1} pins add {0} --position <n> --height <h>".format(
                args.lock_id, PROG
            )
        )
        return EXIT_OK

    title_block("{} - pin stack".format(lock_label(lock)))
    rows = [
        [str(pin.get("position", "")), str(pin.get("height", "")), str(pin.get("note", ""))]
        for pin in pins
    ]
    render_table(["POS", "HEIGHT", "NOTE"], rows, numeric=(0, 1))
    emit("  total  {} pins on the 0-9 height scale".format(len(pins)))
    return EXIT_OK


# --------------------------------------------------------------------------
# Commands: practice
# --------------------------------------------------------------------------


def cmd_practice_start(args: argparse.Namespace) -> int:
    usage = USAGE["practice start"]
    path = store_path()
    store = load_store(path)

    lock = None
    if args.lock_id is not None:
        lock = require_lock(store, args.lock_id, usage)

    active = running_session(store)
    if active is not None:
        active_lock_id = active.get("lock_id")
        fail(
            "a timer is already running for {} since {} - end it with: {} practice stop --success|--failure".format(
                lock_label(find_lock(store, int(active_lock_id)) if active_lock_id else None),
                active.get("started_at", "?"),
                PROG,
            ),
            usage,
        )

    session = {
        "id": allocate_id(store, "sessions"),
        "lock_id": args.lock_id,
        "started_at": utc_now_iso(),
        "started_monotonic": time.monotonic(),
        "ended_at": None,
        "duration_seconds": None,
        "success": None,
    }
    store["sessions"].append(session)
    save_store(path, store)

    emit(
        "timer running for {0} - session {1} started {2} (stop it with: {3} practice stop --success|--failure)".format(
            lock_label(lock), accent(str(session["id"])), session["started_at"], PROG
        )
    )
    return EXIT_OK


def elapsed_seconds(session: Dict[str, Any]) -> Tuple[int, bool]:
    """Return (seconds, estimated) for the running session.

    time.monotonic() is not comparable across a reboot, so when the stored
    start clock lies in the future of the current monotonic clock we fall back
    to the wall-clock difference and flag the duration as an estimate.
    """
    started_monotonic = session.get("started_monotonic")
    now_monotonic = time.monotonic()
    estimated = False

    if isinstance(started_monotonic, (int, float)) and now_monotonic >= float(started_monotonic):
        delta = now_monotonic - float(started_monotonic)
    else:
        estimated = True
        started_at = parse_iso(str(session.get("started_at", "")))
        delta = 0.0 if started_at is None else (datetime.now(timezone.utc) - started_at).total_seconds()

    seconds = int(round(max(delta, 0.0)))
    if seconds == 0 and delta > 0:
        seconds = 1
    return seconds, estimated


def cmd_practice_stop(args: argparse.Namespace) -> int:
    usage = USAGE["practice stop"]
    path = store_path()
    store = load_store(path)

    session = running_session(store)
    if session is None:
        fail("no timer is running - start one with: {} practice start [<lock_id>]".format(PROG), usage)

    success = bool(args.success)
    seconds, estimated = elapsed_seconds(session)
    session["duration_seconds"] = seconds
    session["success"] = success
    session["ended_at"] = utc_now_iso()
    save_store(path, store)

    lock = find_lock(store, int(session["lock_id"])) if session.get("lock_id") else None
    outcome = "opened" if success else "not opened"
    suffix = " (estimated from the wall clock after a reboot)" if estimated else ""
    emit(
        "session {} complete: {} in {} for {}{}".format(
            accent(str(session["id"])), outcome, humanise_duration(seconds), lock_label(lock), suffix
        )
    )
    return EXIT_OK


def cmd_practice_stats(args: argparse.Namespace) -> int:
    usage = USAGE["practice stats"]
    path = store_path()
    store = load_store(path)

    lock = None
    if args.lock_id is not None:
        lock = require_lock(store, args.lock_id, usage)

    sessions = [
        session
        for session in store["sessions"]
        if session.get("success") is not None and session.get("duration_seconds") is not None
    ]
    if lock is not None:
        sessions = [session for session in sessions if session.get("lock_id") == lock["id"]]

    if not sessions:
        if lock is None:
            emit("no sessions recorded yet - start a timer with: {} practice start [<lock_id>]".format(PROG))
        else:
            emit(
                "no completed sessions for lock {0} yet - start a timer with: {1} practice start {0}".format(
                    lock["id"], PROG
                )
            )
        return EXIT_OK

    opened = [session for session in sessions if session.get("success")]
    rate = int(round(100.0 * len(opened) / len(sessions)))
    if opened:
        average = int(round(sum(int(session["duration_seconds"]) for session in opened) / len(opened)))
        average_text = humanise_duration(average)
    else:
        average_text = "n/a (nothing opened yet)"

    heading = "practice stats" if lock is None else "practice stats - {}".format(lock_label(lock))
    title_block(heading)
    render_fields(
        [
            ("sessions", str(len(sessions))),
            ("opened", str(len(opened))),
            ("success rate", "{}% ({} of {})".format(rate, len(opened), len(sessions))),
            ("avg open time", average_text),
        ],
        accent_keys=("success rate",),
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


class OneLineParser(argparse.ArgumentParser):
    """An ArgumentParser whose failures are one line naming the usage form."""

    usage_form = USAGE["root"]

    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        raise UsageError(message, self.usage_form)


def positive_int(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("position must be a whole number (got {!r})".format(text))
    if value < 1:
        raise argparse.ArgumentTypeError("position must be 1 or greater (got {!r})".format(text))
    return value


def pin_height(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("height must be a whole number (got {!r})".format(text))
    if not 0 <= value <= 9:
        raise argparse.ArgumentTypeError("height must be between 0 and 9 (got {!r})".format(text))
    return value


def build_parser() -> OneLineParser:
    epilog = """examples:
  {prog} locks add --model "Master 140" --method rake --note "practice padlock"
  {prog} locks list
  {prog} locks show 1
  {prog} pins add 1 --position 1 --height 3 --note "low cut"
  {prog} pins show 1
  {prog} practice start 1
  {prog} practice stop --success
  {prog} practice stats --lock 1

store:
  {prog} keeps one JSON log. Default $HOME/.lockpicklog/data.json, overridden
  with the LOCKPICKLOG_DATA environment variable.

output:
  records go to stdout (one per line, safe to redirect), errors to stderr.
  Colour is only used on a terminal and is disabled by --no-color or NO_COLOR.

exit codes:
  0 success   2 bad input (nothing stored)   1 storage problem (nothing changed)""".format(prog=PROG)

    parser = OneLineParser(
        prog=PROG,
        description="{0} - log your locks, their pin stacks and your pick attempts.".format(AUTHOR),
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.usage_form = USAGE["root"]
    parser.add_argument("--version", action="version", version="{} {}".format(AUTHOR, VERSION))
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colour (the NO_COLOR environment variable is also honoured)",
    )

    subparsers = parser.add_subparsers(dest="group", metavar="<command>", parser_class=OneLineParser)

    # locks ----------------------------------------------------------------
    locks = subparsers.add_parser(
        "locks",
        help="log locks (model and picking method)",
        description="Log the locks you practise on, newest first.",
    )
    locks.usage_form = USAGE["locks"]
    locks.set_defaults(group_parser=locks)
    locks_sub = locks.add_subparsers(dest="action", metavar="<action>", parser_class=OneLineParser)

    locks_add = locks_sub.add_parser(
        "add", help="add one lock and print its new id", description="Add one lock and print its new integer id."
    )
    locks_add.usage_form = USAGE["locks add"]
    locks_add.add_argument("--model", required=True, metavar="<text>", help='lock model, for example "Master 140"')
    locks_add.add_argument("--method", required=True, metavar="<text>", help="picking method, for example rake / spp / bogota")
    locks_add.add_argument("--note", default=None, metavar="<text>", help="optional free-text note")
    locks_add.set_defaults(handler=cmd_locks_add)

    locks_list = locks_sub.add_parser(
        "list", help="list every lock, newest first", description="List every logged lock, most recently added first."
    )
    locks_list.usage_form = USAGE["locks list"]
    locks_list.set_defaults(handler=cmd_locks_list)

    locks_show = locks_sub.add_parser(
        "show", help="show every stored field of one lock", description="Show every stored field of one lock."
    )
    locks_show.usage_form = USAGE["locks show"]
    locks_show.add_argument("lock_id", metavar="<lock_id>", type=int, help="the id printed by 'locks add'")
    locks_show.set_defaults(handler=cmd_locks_show)

    # pins -----------------------------------------------------------------
    pins = subparsers.add_parser(
        "pins",
        help="log a lock's pin tumbler sequence",
        description="Log a lock's pin stack, one position at a time.",
    )
    pins.usage_form = USAGE["pins"]
    pins.set_defaults(group_parser=pins)
    pins_sub = pins.add_subparsers(dest="action", metavar="<action>", parser_class=OneLineParser)

    pins_add = pins_sub.add_parser(
        "add",
        help="add or update one pin position",
        description="Add one pin position, or replace that position's height if it already exists.",
    )
    pins_add.usage_form = USAGE["pins add"]
    pins_add.add_argument("lock_id", metavar="<lock_id>", type=int, help="id of an existing lock")
    pins_add.add_argument("--position", required=True, metavar="<1..n>", type=positive_int, help="pin position, 1 or greater")
    pins_add.add_argument("--height", required=True, metavar="<0-9>", type=pin_height, help="pin height on the 0-9 scale")
    pins_add.add_argument("--note", default=None, metavar="<text>", help="optional free-text note for this pin")
    pins_add.set_defaults(handler=cmd_pins_add)

    pins_show = pins_sub.add_parser(
        "show", help="show a lock's pin stack in position order", description="Show the pin stack in ascending position order."
    )
    pins_show.usage_form = USAGE["pins show"]
    pins_show.add_argument("lock_id", metavar="<lock_id>", type=int, help="id of an existing lock")
    pins_show.set_defaults(handler=cmd_pins_show)

    # practice -------------------------------------------------------------
    practice = subparsers.add_parser(
        "practice",
        help="time attempts and report your success rate",
        description="Time practice attempts and summarise the outcomes.",
    )
    practice.usage_form = USAGE["practice"]
    practice.set_defaults(group_parser=practice)
    practice_sub = practice.add_subparsers(dest="action", metavar="<action>", parser_class=OneLineParser)

    practice_start = practice_sub.add_parser(
        "start", help="start timing a practice attempt", description="Start the timer; the start clock is written to the store immediately."
    )
    practice_start.usage_form = USAGE["practice start"]
    practice_start.add_argument(
        "lock_id", nargs="?", default=None, type=int, metavar="<lock_id>", help="optional lock id to attribute the session to"
    )
    practice_start.set_defaults(handler=cmd_practice_start)

    practice_stop = practice_sub.add_parser(
        "stop", help="stop the timer and record the outcome", description="Stop the running timer and record whether the lock opened."
    )
    practice_stop.usage_form = USAGE["practice stop"]
    outcome = practice_stop.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--success", action="store_true", help="the lock opened")
    outcome.add_argument("--failure", action="store_true", help="the lock did not open")
    practice_stop.set_defaults(handler=cmd_practice_stop)

    practice_stats = practice_sub.add_parser(
        "stats", help="report sessions, success rate and average open time", description="Report totals, success rate and average open time."
    )
    practice_stats.usage_form = USAGE["practice stats"]
    practice_stats.add_argument("--lock", dest="lock_id", default=None, type=int, metavar="<lock_id>", help="restrict the report to one lock")
    practice_stats.set_defaults(handler=cmd_practice_stats)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)

    try:
        args = parser.parse_args(raw)
    except UsageError as exc:
        print("error: {}; usage: {}".format(exc.message, exc.usage), file=sys.stderr)
        return EXIT_USAGE

    use_colour(not getattr(args, "no_color", False) and _wants_colour())

    handler: Optional[Callable[[argparse.Namespace], int]] = getattr(args, "handler", None)
    if handler is None:
        # A bare or partial invocation is help-first: print the relevant help
        # and exit 0 rather than failing on a missing subcommand.
        group_parser = getattr(args, "group_parser", None)
        (group_parser or parser).print_help()
        return EXIT_OK

    try:
        return handler(args)
    except UsageError as exc:
        print("error: {}; usage: {}".format(exc.message, exc.usage), file=sys.stderr)
        return EXIT_USAGE
    except StorageError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return EXIT_STORAGE
    except BrokenPipeError:
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
