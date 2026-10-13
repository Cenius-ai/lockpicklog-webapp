#!/usr/bin/env bash
#
# LockpickLog - non-interactive end-to-end walkthrough.
#
# Runs the real CLI against a throwaway store in ./.demo-store, prints the
# transcript, then removes the throwaway store again. Your own log in
# $HOME/.lockpicklog/data.json is never touched. Exits 0 when the whole
# walkthrough has run; the deliberately failing commands are expected to
# report exit 2 (bad input) or exit 1 (corrupt store) and are marked as such.
#
# Output is plain text whenever stdout is not a terminal, so the capture in
# demo/session.txt is reproducible. On a real terminal the one committed
# accent (oklch(0.58 0.12 43) / #b4603c) highlights the rules and the primary
# status values.
#
# Usage:  bash demo.sh

set -u
cd "$(dirname "$0")" || exit 1

PYTHON_BIN="${PYTHON:-python3}"
STORE_DIR=".demo-store"
export LOCKPICKLOG_DATA="$STORE_DIR/data.json"
export PYTHONUNBUFFERED=1

cleanup() { rm -rf "$STORE_DIR"; }
trap cleanup EXIT INT TERM
cleanup
mkdir -p "$STORE_DIR"

run() {
    printf '\n$ %s lockpicklog.py' "$PYTHON_BIN"
    for arg in "$@"; do
        case "$arg" in
            *" "*) printf " '%s'" "$arg" ;;
            *) printf ' %s' "$arg" ;;
        esac
    done
    printf '\n'
    "$PYTHON_BIN" lockpicklog.py "$@"
    status=$?
    if [ "$status" -ne 0 ]; then
        printf '(exit %s - nothing was stored)\n' "$status"
    fi
    return 0
}

printf '# LockpickLog walkthrough - every command below runs the real CLI\n'
printf '# against a throwaway store at %s\n' "$LOCKPICKLOG_DATA"

printf '\n## help first\n'
run --version
run --help

printf '\n## 1. a fresh log invites its first lock\n'
run locks list
run locks add --model "Master 140" --method rake --note "cheap practice padlock"
run locks add --model "ABUS 55/40" --method spp --note "worn pins, needs light tension"
run locks list
run locks show 1

printf '\n## 2. pin tumbler sequence notes\n'
run pins add 1 --position 1 --height 3 --note "low cut"
run pins add 1 --position 2 --height 5
run pins add 1 --position 3 --height 4 --note "spool"
run pins add 1 --position 2 --height 7
run pins show 1

printf '\n## 3. bad input is refused and stores nothing\n'
run pins add 1 --position 1 --height 12
run pins add 1 --position abc --height 3
run pins add 9999 --position 1 --height 3
run locks add --model "" --method rake
run pins show 1

printf '\n## 4. timed attempts\n'
run practice start 1
sleep 2
run practice stop --success
run practice start 2
sleep 2
run practice stop --failure
run practice stop --success
run practice stats
run practice stats --lock 1

printf '\n## 5. the log on disk (schema_version + entity lists, written atomically)\n'
printf '$ head -8 %s\n' "$LOCKPICKLOG_DATA"
head -8 "$LOCKPICKLOG_DATA"

printf '\n## 6. a corrupted log fails loudly and is left untouched\n'
printf '$ printf %s > %s\n' "'not json'" "$LOCKPICKLOG_DATA"
printf 'not json\n' > "$LOCKPICKLOG_DATA"
run locks list

printf '\n# Walkthrough complete. Your own log at $HOME/.lockpicklog/data.json was never touched.\n'
exit 0
