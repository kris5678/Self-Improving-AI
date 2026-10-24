#!/bin/sh
# Updates the self-review trend report and opens it (no AI, no tokens). macOS / Linux.
dir="$(cd "$(dirname "$0")" && pwd)"
python3 -I "$dir/benchmark_summary.py" || { echo "Could not update the report."; exit 1; }
report="$dir/../../self-review-trend.html"
if command -v open >/dev/null 2>&1; then open "$report"; else xdg-open "$report"; fi
