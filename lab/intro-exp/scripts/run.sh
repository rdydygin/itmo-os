#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x out/venv/bin/python ]]; then
  python3 -m venv out/venv
fi
out/venv/bin/python -m pip --version >/dev/null 2>&1 || out/venv/bin/python -m ensurepip
out/venv/bin/python -m pip install -r scripts/requirements.txt
out/venv/bin/python scripts/experiment.py all "$@"
out/venv/bin/python scripts/analyze.py
out/venv/bin/python report/generate.py
