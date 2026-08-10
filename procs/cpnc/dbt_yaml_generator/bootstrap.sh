#!/usr/bin/env bash
# One-command setup for a machine WITHOUT an existing Python env.
# If you already have your dbt venv, skip this and just:
#   pip install -r procs/cpnc/requirements.txt
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
py="$here/.venv/bin/python"

echo "Creating venv at $here/.venv ..."
python3 -m venv "$here/.venv"
"$py" -m pip install --upgrade pip
"$py" -m pip install -r "$here/../requirements-dev.txt"

echo "Running offline tests ..."
"$py" -m pytest "$here/tests"
echo "OK — package is working. Next: copy config.example.yml to config.yml and edit it."
