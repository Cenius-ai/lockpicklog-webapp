# Using LockpickLog

Task-by-task recipes. Every command is `python3 lockpicklog.py <command>`;
substitute `python3` for whichever interpreter you use. Records go to stdout,
errors to stderr, and nothing is written when a command fails.

Set `LOCKPICKLOG_DATA=/path/to/log.json` on any command to use a log other than
`$HOME/.lockpicklog/data.json`.

## Log a lock you own or borrowed

```bash
python3 lockpicklog.py locks add --model "Master 140" --method rake --note "cheap practice padlock"
# added lock 1 - Master 140 (rake)
```

`--model` and `--method` are required and must not be blank. `--note` is
optional and free text - put the tension you needed, where it came from, how
worn it is, anything you would forget.

Browse what you have:

```bash
python3 lockpicklog.py locks list      # newest first, with pin counts
python3 lockpicklog.py locks show 1    # every stored field
```

On a brand-new log `locks list` prints
`no locks logged yet - add one with: lockpicklog locks add --model <text> --method <text>`
and exits 0.

## Note a pin tumbler sequence

Add the stack one pin at a time. `--position` counts from the front of the lock
starting at 1; `--height` is the pin's length on the 0-9 scale.

```bash
python3 lockpicklog.py pins add 1 --position 1 --height 3 --note "low cut"
python3 lockpicklog.py pins add 1 --position 2 --height 7
python3 lockpicklog.py pins add 1 --position 3 --height 4 --note "spool, holds a false set"
python3 lockpicklog.py pins show 1
```

```
lock 1 - Master 140 - pin stack
───────────────────────────────
  POS  HEIGHT  NOTE
  ───  ──────  ───────
    1       3  low cut
    2       7
    3       4  spool, holds a false set
  total  3 pins on the 0-9 height scale
```

Got a height wrong? Log the position again - it updates that pin instead of
duplicating it:

```bash
python3 lockpicklog.py pins add 1 --position 2 --height 5
# updated position 2 for lock 1 - height is now 5 (no duplicate created)
```

Omit `--note` when updating to keep the note you already stored; pass
`--note "new text"` to replace it.

## Time your attempts

```bash
python3 lockpicklog.py practice start 1
# timer running for lock 1 - Master 140 - session 1 started ... (stop it with: ...)

# ... pick the lock ...

python3 lockpicklog.py practice stop --success
# session 1 complete: opened in 42s for lock 1 - Master 140
```

Use `--failure` when it did not open. Everything is written to disk at
`practice start`, so the two commands can be minutes or hours apart, in
different terminals or after a reboot (a reboot makes the duration an estimate,
and the command says so).

Leave the lock id off to record an unattributed session:

```bash
python3 lockpicklog.py practice start
python3 lockpicklog.py practice stop --failure
# session 2 complete: not opened in 18s for unattributed
```

Only one timer runs at a time; starting a second while one is running is refused
and stores nothing.

## Read your success rate

```bash
python3 lockpicklog.py practice stats
```

```
practice stats
──────────────
  sessions       6
  opened         4
  success rate   67% (4 of 6)
  avg open time  38s
```

Restrict it to one lock to see whether *that* one is getting easier:

```bash
python3 lockpicklog.py practice stats --lock 1
```

`sessions` counts completed attempts only (a running timer is not counted until
you stop it), `opened` counts the successes, `success rate` is opened over
sessions, and `avg open time` is the mean open time over the **opened** sessions
only - a failure has no open time to average. With no completed sessions yet the
command prints an invitation instead of a report, and still exits 0.

## Script it

Everything is line-based and pipe-friendly, so it drops into a shell script or a
transcript:

```bash
python3 lockpicklog.py locks list > tonight.txt
python3 lockpicklog.py practice stats >> tonight.txt
```

## Clean up

The tool never deletes records. To start over, move or delete the log:

```bash
mv "$HOME/.lockpicklog/data.json" "$HOME/.lockpicklog/data.json.bak"
```

The next command creates a fresh, empty log automatically.
