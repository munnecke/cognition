#!/bin/bash
# Quick diagnostic. Double-click this. It clears the stale cache from the last
# run, then probes a few search-URL variants against the American Presidency
# Project and saves the pages so Claude can confirm the exact working format.
# Takes about 10-20 seconds.

cd "$(dirname "$0")" || exit 1

echo "=============================================================="
echo "  Presidential Cognition Corpus — Site Diagnostic"
echo "=============================================================="

if [ ! -d ".venv" ]; then
  echo "!! Setup hasn't been run yet. Double-click '1 — Setup & Test.command' first."
  read -r -p "Press Return to close."
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo ">> Clearing stale cache and state from the previous run..."
rm -rf .cache/http .cache/state_app.json data_raw/_diag 2>/dev/null

echo ">> Probing search-URL variants (Reagan)..."
python scripts/collect_app.py --diagnose

echo
echo "=============================================================="
echo "  Done. Saved pages are in data_raw/_diag/"
echo "  Send Claude the lines above (the 'doc links | title=' lines)."
echo "  Claude can also read the saved files directly from your folder."
echo "=============================================================="
echo
read -r -p "Press Return to close this window."
