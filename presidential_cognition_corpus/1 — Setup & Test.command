#!/bin/bash
# Double-click this file in Finder. It sets everything up and runs a small test.
# No typing required.

cd "$(dirname "$0")" || exit 1

echo "=============================================================="
echo "  Presidential Cognition Corpus — Setup & Test"
echo "=============================================================="
echo "Working folder: $(pwd)"
echo

# --- find Python 3 ---------------------------------------------------------
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "!! Python 3 was not found on this Mac."
  echo "   Install it from https://www.python.org/downloads/ (or 'brew install python'),"
  echo "   then double-click this file again."
  echo
  read -r -p "Press Return to close."
  exit 1
fi
echo "Using Python: $($PY --version)"

# --- create / reuse virtual environment ------------------------------------
if [ ! -d ".venv" ]; then
  echo "Creating an isolated environment (.venv)..."
  "$PY" -m venv .venv || { echo "Could not create venv."; read -r -p "Press Return."; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- install CORE dependencies (required) ----------------------------------
echo
echo ">> Installing core packages (this can take a few minutes the first time)..."
python -m pip install --upgrade pip >/dev/null
if ! pip install -r requirements.txt; then
  echo "!! Core package install failed. Scroll up to see why, and send it to Claude."
  read -r -p "Press Return to close."
  exit 1
fi

# --- install OPTIONAL dependencies (best effort; never blocks) -------------
echo
echo ">> Installing optional ML packages (spaCy, embeddings, local-LLM client)."
echo "   If any fail (e.g. no wheel yet for a very new Python), that's OK —"
echo "   the collector still runs without them."
pip install -r requirements-optional.txt || echo "   (some optional packages skipped — continuing)"

# --- language data (best effort; pipeline still works without it) ----------
echo
echo ">> Downloading language data (spaCy model + readability)..."
python -m spacy download en_core_web_sm || echo "   (spaCy model optional — continuing)"
python -m nltk.downloader cmudict       || echo "   (readability data optional — continuing)"

# --- connectivity + president mapping check --------------------------------
echo
echo "=============================================================="
echo "  CHECK 1: Can we reach the American Presidency Project, and"
echo "  does each president map to a site ID?"
echo "=============================================================="
python scripts/collect_app.py --list-people

# --- smoke test: a few documents end to end --------------------------------
echo
echo "=============================================================="
echo "  CHECK 2: Collect 5 documents per president and run the full"
echo "  pipeline (clean -> dedupe -> classify -> metrics -> report)."
echo "=============================================================="
python scripts/run_pipeline.py --sources app --limit 5

echo
echo "=============================================================="
echo "  RESULT"
echo "=============================================================="
if [ -f data_clean/metadata.csv ]; then
  ROWS=$(($(wc -l < data_clean/metadata.csv) - 1))
  echo "  Collected $ROWS transcripts in this test."
  echo "  Metadata : data_clean/metadata.csv"
  echo "  Texts    : data_clean/speeches/"
  echo "  Report   : logs/collection_report.md"
  echo
  echo "  If those numbers look reasonable, double-click"
  echo "  '2 — Collect Everything.command' to run the full collection."
  echo
  echo "  If anything looks wrong, send the output above to Claude."
else
  echo "  No metadata was produced. Send the output above to Claude so"
  echo "  the scraper can be adjusted."
fi
echo
read -r -p "Press Return to close this window."
