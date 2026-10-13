#!/usr/bin/env bash
#
# LockpickLog setup - run with:  bash install.sh
#
# Installs the optional test runner, verifies that the tool itself imports, and
# EXITS. It never starts a server (there is no server) and never seeds your
# personal log (a fresh log is created by the tool itself on first use).

set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"

echo "LockpickLog setup"
echo "-----------------"
"$PYTHON_BIN" --version

# The tool is standard library only: this step exists solely for the pytest
# suite in tests/. Nothing is downloaded when the runner is already present.
if "$PYTHON_BIN" -c "import pytest" >/dev/null 2>&1; then
    echo "test runner: pytest already available, nothing to install"
else
    echo "test runner: installing pytest (the tool itself needs no packages)"
    "$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

# Cheap self-check: a missing module must fail here, not at first run.
"$PYTHON_BIN" -c "import lockpicklog; print('self-check: lockpicklog imports cleanly')"
"$PYTHON_BIN" lockpicklog.py --version

cat <<'EOF'

Setup complete - there is no server to start and no migration to run.

  Use it now      python3 lockpicklog.py --help
  Try the demo    bash demo.sh
  Run the tests   python3 -m pytest
  Your log        $HOME/.lockpicklog/data.json  (override: LOCKPICKLOG_DATA)

EOF
