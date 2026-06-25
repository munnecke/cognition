#!/usr/bin/env bash
# run_spontaneity_overnight.sh — resilient, resumable corpus-wide spontaneity scoring.
#
# Scores EVERY canonical speech (>=200 words, all presidents, all genres) with the
# LLM spontaneity classifier, in bounded batches so memory stays flat and a crash
# loses at most one batch. Fully idempotent: each batch uses --only-missing, so
# re-running (after a crash, a server restart, or on a later night) picks up
# exactly where it left off. Survives an overnight LM Studio hiccup: per-doc
# errors skip+retry; if a whole batch makes NO progress for STUCK_LIMIT passes
# (server down), it stops instead of hot-looping a dead endpoint.
#
# Usage:  scripts/run_spontaneity_overnight.sh            # all presidents/genres
#         (override scope by editing EXTRA_ARGS below, e.g. --presidents trump)
#
# Watch:  tail -f logs/spontaneity_overnight.log
# Stop:   touch /tmp/STOP_SPONTANEITY   (checked between batches) — or pkill -f llm_spontaneity

set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true

# Must match llm_spontaneity.py defaults (the (model, prompt_version) key).
MODEL="${LLM_MODEL:-josiefied-qwen2.5-7b-instruct-abliterated-v2-4-bit}"
PROMPT_VERSION="spontaneity-v2"
BATCH=500
STUCK_LIMIT=3            # consecutive no-progress batches before giving up
SLEEP_BETWEEN=8
EXTRA_ARGS=""           # e.g. "--presidents trump" to scope; empty = whole corpus

LOG=logs/spontaneity_overnight.log
mkdir -p logs
STOP_FLAG=/tmp/STOP_SPONTANEITY
rm -f "$STOP_FLAG"

remaining() {
  psql presidential_speech -t -A -c \
    "select count(*) from speeches s
     where s.is_canonical and s.presidential_voice and s.word_count>=200
       and not exists (select 1 from llm_extractions e
                       where e.speech_id=s.id and e.extraction_type='spontaneity'
                         and e.prompt_version='${PROMPT_VERSION}' and e.model='${MODEL}')"
}

echo "=== overnight spontaneity run started $(date) ===" | tee -a "$LOG"
echo "model=$MODEL prompt=$PROMPT_VERSION batch=$BATCH scope='${EXTRA_ARGS:-ALL}'" | tee -a "$LOG"
TOTAL_LEFT=$(remaining); echo "remaining to score: $TOTAL_LEFT" | tee -a "$LOG"

stuck=0
while :; do
  [ -f "$STOP_FLAG" ] && { echo "STOP flag seen — exiting $(date)" | tee -a "$LOG"; break; }
  before=$(remaining)
  if [ "$before" -eq 0 ]; then
    echo "=== ALL DONE $(date): nothing left to score ===" | tee -a "$LOG"
    break
  fi
  echo "--- batch start $(date): $before remaining ---" | tee -a "$LOG"
  python scripts/llm_spontaneity.py --only-missing --limit "$BATCH" --model "$MODEL" \
      $EXTRA_ARGS >> "$LOG" 2>&1
  after=$(remaining)
  echo "--- batch end $(date): $after remaining (did $((before-after))) ---" | tee -a "$LOG"
  if [ "$after" -ge "$before" ]; then
    stuck=$((stuck+1))
    echo "no progress ($stuck/$STUCK_LIMIT) — LM Studio may be down; sleeping" | tee -a "$LOG"
    if [ "$stuck" -ge "$STUCK_LIMIT" ]; then
      echo "=== GIVING UP $(date): $STUCK_LIMIT stuck batches. Resume by re-running this script. ===" | tee -a "$LOG"
      break
    fi
    sleep 60
  else
    stuck=0
    sleep "$SLEEP_BETWEEN"
  fi
done
echo "=== runner exited $(date) ===" | tee -a "$LOG"
