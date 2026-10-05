#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p output/pdf
out/venv/bin/python scripts/report_figures.py
typst compile --root . report/main.typ output/pdf/report-gost.pdf
