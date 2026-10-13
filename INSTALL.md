# Install and run LockpickLog

LockpickLog is a single Python file that uses only the standard library. There
is nothing to compile, no server to start and no database to provision.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.9 or newer | `python3 --version`. Developed on Python 3.11. |
| `pip` | Only to install the optional test runner (pytest). Not needed to run the tool. |

Nothing else is required - no system packages, no compiler, no database engine,
no lockfile beyond the pinned `requirements.txt`.

## Package manager

`pip` with the committed `requirements.txt`. Do not mix in a second package
manager; the only declared dependency is the test runner.

## Steps

### 1. Install (optional - only the test runner)

```bash
bash install.sh
```

`install.sh` upgrades pip/setuptools/wheel only when it has to install
something, installs `requirements.txt` (pytest) if the runner is missing,
verifies the tool imports, prints its version, and then exits. It never starts a
process in the foreground and never touches your log file.

You can skip this step entirely if you only want to use the tool - running
`python3 lockpicklog.py` needs no packages at all.

Doing it by hand instead:

```bash
python3 -m pip install -r requirements.txt   # pytest only
```

### 2. Migrate

Not applicable. The log file's schema is created by the tool itself the first
time any command runs; there is no migration step.

### 3. Seed / demo data

The tool starts empty on purpose: it is *your* practice log. To see every
command work end to end against realistic data, run the scripted walkthrough,
which uses a throwaway log in `./.demo-store` and deletes it afterwards:

```bash
bash demo.sh
```

The captured output is committed as `demo/session.txt`.

### 4. Run

Every command is the same shape - there is no server, so there is no start
command to leave running:

```bash
python3 lockpicklog.py --help
python3 lockpicklog.py locks add --model "Master 140" --method rake
python3 lockpicklog.py locks list
python3 lockpicklog.py pins add 1 --position 1 --height 3 --note "low cut"
python3 lockpicklog.py pins show 1
python3 lockpicklog.py practice start 1
python3 lockpicklog.py practice stop --success
python3 lockpicklog.py practice stats
```

By default the log is written to `$HOME/.lockpicklog/data.json`. Point it
somewhere else with `LOCKPICKLOG_DATA`:

```bash
LOCKPICKLOG_DATA=./my-log.json python3 lockpicklog.py locks list
```

There is no login and no account: a single-user local file tool has nothing to
authenticate. Local file permissions are the boundary (the log is created
`0600`).

### 5. Test

```bash
python3 -m pytest
```

Offline, non-interactive, no external services; the fixtures build their own
throwaway logs under the pytest temporary directory.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `error: store ... is not valid JSON` | The log file was edited or truncated by hand. Fix it, or move it aside - the tool will create a fresh one. Exit code 1. |
| `error: store ... has unsupported schema_version N` | The file was written by a different version of the tool. Exit code 1; the file is left untouched. |
| `error: no timer is running` | `practice stop` without a matching `practice start`. Exit code 2, nothing recorded. |
| `error: a timer is already running` | Only one attempt is timed at a time; finish it with `practice stop --success` or `--failure`. |
| Colour codes in a redirected file | Set `NO_COLOR=1` or pass `--no-color`; colour is off automatically when stdout is not a terminal. |
