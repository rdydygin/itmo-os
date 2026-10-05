#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
trace_dir="${1:-mac-check-20261005-100726}"
mkdir -p results/system-trace
query='/trace-toc/run[@number="1"]/data/table[@schema="thread-state" or @schema="context-switch" or @schema="syscall-name-map" or @schema="time-profile"]'
for name in graph_traverse-read graph_traverse-write graph_traverse_mmap-read graph_traverse_mmap-write; do
  xcrun xctrace export --input "$trace_dir/$name.trace" --toc \
    --output "results/system-trace/$name-toc.xml"
  xcrun xctrace export --input "$trace_dir/$name.trace" --xpath "$query" \
    --output "results/system-trace/$name-data.xml"
done
out/venv/bin/python scripts/analyze_traces.py
