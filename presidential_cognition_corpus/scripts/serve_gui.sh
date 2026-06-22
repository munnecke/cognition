#!/usr/bin/env bash
# serve_gui.sh — start the web GUIs that query PostgreSQL directly (no mirror).
#
#   marimo dashboard  ->  http://localhost:2718   (analytical, reuses our code)
#   pgweb browser     ->  http://localhost:8081   (read-only tables + SQL)
#
# Postgres (presidential_speech) is the single source of truth; both tools query
# it live. Stop with: pkill -f 'marimo run' ; pkill -f pgweb
set -euo pipefail
cd "$(dirname "$0")/.."

DB="${PG_DB:-presidential_speech}"
mkdir -p logs

echo "marimo dashboard -> http://localhost:2718"
PG_DB="$DB" nohup marimo run scripts/dashboard.py --headless --host 127.0.0.1 --port 2718 \
  > logs/marimo.out 2>&1 &

echo "pgweb browser    -> http://localhost:8081"
nohup pgweb --url "postgresql:///${DB}?sslmode=disable" --bind 127.0.0.1 --listen 8081 --readonly \
  > logs/pgweb.out 2>&1 &

echo "Both starting in the background. Logs: logs/marimo.out, logs/pgweb.out"
