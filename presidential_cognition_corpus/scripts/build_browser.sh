#!/usr/bin/env bash
# build_browser.sh — refresh the Datasette browser from Postgres.
#
# Postgres is the system of record; Datasette browses a SQLite mirror. This
# script (re)loads Postgres from the flat files, exports a SQLite snapshot,
# enables full-text search, and serves it. Re-run any time the corpus grows.
#
# Usage:
#   scripts/build_browser.sh            # load -> export -> enable FTS -> serve
#   scripts/build_browser.sh --no-serve # build the SQLite mirror only
set -euo pipefail
cd "$(dirname "$0")/.."

DB="${PG_DB:-presidential_speech}"
SQLITE="data_clean/corpus.db"
PORT="${DATASETTE_PORT:-8001}"

echo "[1/4] Loading Postgres ($DB) from flat files..."
python scripts/load_to_postgres.py --db "$DB"

echo "[2/4] Exporting SQLite mirror -> $SQLITE ..."
rm -f "$SQLITE"
db-to-sqlite "postgresql:///$DB" "$SQLITE" --all

echo "[3/4] Enabling full-text search on speeches(title, full_text)..."
sqlite-utils enable-fts "$SQLITE" speeches title full_text --fts5 || true

if [[ "${1:-}" == "--no-serve" ]]; then
  echo "Done (mirror built; not serving)."
  exit 0
fi

echo "[4/4] Serving Datasette at http://localhost:$PORT ..."
exec datasette "$SQLITE" \
  --metadata scripts/datasette_metadata.yaml \
  --setting sql_time_limit_ms 8000 \
  --setting facet_time_limit_ms 3000 \
  --port "$PORT"
