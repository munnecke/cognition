#!/bin/bash
# Double-click to run the FULL collection (American Presidency Project + Miller
# Center), then clean / dedupe / classify / measure / report.
#
# Safe to stop and restart: it resumes where it left off and never re-downloads
# what it already has. Run it again any time to pick up new material.

cd "$(dirname "$0")" || exit 1

echo "=============================================================="
echo "  Presidential Cognition Corpus — Full Collection"
echo "=============================================================="

if [ ! -d ".venv" ]; then
  echo "!! Setup hasn't been run yet."
  echo "   Double-click '1 — Setup & Test.command' first."
  read -r -p "Press Return to close."
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "This downloads thousands of transcripts and may run for a long time."
echo "You can close the window to stop; double-click this file again to resume."
echo
read -r -p "Press Return to begin (or close the window to cancel)."

python scripts/run_pipeline.py --sources app miller

echo
echo "=============================================================="
if [ -f data_clean/metadata.csv ]; then
  ROWS=$(($(wc -l < data_clean/metadata.csv) - 1))
  echo "  Collection pass complete. Total transcripts: $ROWS"
  echo "  See logs/collection_report.md for counts by president/year/source/type."
else
  echo "  No metadata produced — send Claude the output above."
fi
echo "=============================================================="
echo
read -r -p "Press Return to close this window."
