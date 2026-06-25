"""
llm_spontaneity.py — LLM-scored spontaneity of each transcript.

WHY
---
The Berisha-style longitudinal markers (`replicate_berisha.py`) only mean
anything on *spontaneous* presidential speech — answers to questions, not
speechwriter-authored addresses. Until now the "impromptu" set was defined
structurally: title says "news conference" + a Q&A label is present
(`classify_event_type.py`). That filter is brittle and *small* — e.g. Trump's
2nd term has only ~10 titled news conferences, too few to regress.

This script is the smarter selector. It reads the actual text and asks a LOCAL
model (gemma-4-26b via `llm.py` — see the model-choice note below; the 3B model
was too weak) to score, per transcript, *how spontaneous the president's speech
is* on a 0..1 scale. The impromptu set is
then `spontaneity >= threshold`, which pulls in exchanges-with-reporters, Q&A,
interviews, town halls and debates already in the corpus — a bigger, fairer
sample than the title filter — while still excluding scripted addresses.

Division of labor (kept deliberately separate, see HANDOFF):
  * `classify_event_type.prepared_or_impromptu`  = deterministic STRUCTURAL label
    on title/structure, stored in `speeches` metadata. Never moves.
  * THIS score                                   = INTERPRETIVE, model-judged,
    stored in `llm_extractions` with model + prompt_version provenance, so a
    model/prompt change can't silently move the longitudinal trend lines.

Downstream, `segment_speaker.president_answers()` still runs on whatever this
selects — this picks the *events*; that extracts the president-only answers.

STORAGE
-------
One row per (speech, model, prompt_version) in `llm_extractions`:
    extraction_type   = "spontaneity"
    extracted_pattern = label  (scripted | mixed | spontaneous)
    confidence_score  = spontaneity (0..1)
    raw               = full parsed JSON + excerpt provenance

USAGE
-----
    # eyeball a handful WITHOUT writing (start small, measure):
    python llm_spontaneity.py --sample 8

    # score the genres that plausibly contain spontaneous speech, missing only:
    python llm_spontaneity.py --only-missing --types press_conference q_and_a \
        interview town_hall debate roundtable

    # everything, restartable:
    python llm_spontaneity.py --only-missing

Operational note (see HANDOFF "Caution"): LLM batch jobs are memory/time heavy.
Each transcript is capped to a head+middle excerpt (`--max-words`) so long Trump
transcripts can't blow up latency/memory. Start with --sample / --limit, watch
the throughput line, then scale.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time

import psycopg

import common as C
from llm import get_llm

LOG = C.get_logger("spontaneity")

# Model choice — benchmarked on a labelled 6-doc set (scripted/mixed/spontaneous),
# accuracy AND throughput:
#   * llama-3.2-3b      — can't discriminate (constant "mixed"); rejected.
#   * gemma-4-26b-a4b   — accurate (5/6) but a *reasoning* model with sliding-
#       window attention: its prompt cache can't be reused, so the full ~2.3k-tok
#       prompt is re-encoded every doc → ~11 s/doc, untenable at corpus scale.
#   * gte-qwen2-7b      — an embedding model; emits non-JSON and degenerates.
#   * Qwen2.5-7B-Instruct (4-bit MLX) — 5/6 with the v2 prompt, clean JSON, and
#       ~3-5 s/doc (non-SWA → prefix cache works; MLX is fast on Apple Silicon).
# Winner: Qwen2.5-7B-Instruct. The id below is the locally-loaded community build;
# the stock `Qwen2.5-7B-Instruct` MLX 4-bit is the reproducible equivalent.
# Override with --model / LLM_MODEL.
DEFAULT_SPONTANEITY_MODEL = os.environ.get(
    "LLM_MODEL", "josiefied-qwen2.5-7b-instruct-abliterated-v2-4-bit")

EXTRACTION_TYPE = "spontaneity"
# v2: sharpened the mixed-vs-spontaneous boundary (a brief framing before pure
# Q&A is spontaneous, not mixed) — recovered the 0.8-1.0 band Qwen had collapsed
# to 0.5. Bump this whenever the prompt/scale changes so scores stay comparable.
PROMPT_VERSION = "spontaneity-v2"
LABELS = ("scripted", "mixed", "spontaneous")

# Token budget for the JSON answer (Qwen2.5 is not a reasoning model, so it needs
# far less than gemma did; 400 is comfortable headroom for reason+evidence).
MAX_TOKENS = 400
# Per-request timeout (s): bounds a hung generation / server hiccup so the
# batch can't block forever (a server restart mid-run hung the whole job).
REQUEST_TIMEOUT = 90.0

_WS = re.compile(r"\s+")

SYSTEM = (
    "You are a linguist classifying U.S. presidential transcripts by how "
    "SPONTANEOUS the president's own speech is — i.e. how much of it is "
    "unscripted, extemporaneous talk rather than a speechwriter-authored text "
    "read aloud.\n\n"
    "Scale — judge by the BALANCE of prepared vs unscripted material:\n"
    "  scripted    — a prepared address read aloud (inaugural, State of the "
    "Union, radio/weekly address, formal statement). No unscripted Q&A. "
    "spontaneity 0.0-0.2.\n"
    "  mixed       — roughly BALANCED: a SUBSTANTIAL prepared opening AND a "
    "comparable amount of Q&A (a typical formal news conference with a long "
    "statement, then questions). spontaneity 0.4-0.6.\n"
    "  spontaneous — PREDOMINANTLY unscripted: most of the text is the president "
    "answering reporters' questions or an interviewer, an exchange with "
    "reporters, a town hall, a debate, off-the-cuff banter. A brief one- or "
    "two-line framing before the Q&A still counts as spontaneous, NOT mixed — "
    "only a substantial prepared statement makes it mixed. spontaneity 0.8-1.0.\n\n"
    "Judge the PRESIDENT's speech, not other speakers. Reporter questions and "
    "back-and-forth turns ('Q.', 'QUESTION', 'The President.'/'The President:') "
    "are strong evidence of spontaneous Q&A.\n\n"
    "IMPORTANT: a long prepared OPENING does NOT make a transcript 'scripted'. "
    "If the president then answers reporters' questions, it is 'mixed' (or "
    "'spontaneous' if the answers dominate). Read the whole excerpt — the Q&A "
    "often starts after the opening statement."
)

USER_TEMPLATE = (
    "Transcript title: {title}\n"
    "Catalogued event type: {etype}\n\n"
    "--- transcript excerpt (head, then a middle slice) ---\n"
    "{excerpt}\n"
    "--- end excerpt ---\n\n"
    "Return ONLY a JSON object with these keys, in this order:\n"
    '  "reason": one sentence on what you saw (an opening statement? reporter '
    'questions? an interview?),\n'
    '  "interactive": true if the president answers unscripted questions, else false,\n'
    '  "label": one of "scripted" / "mixed" / "spontaneous",\n'
    '  "spontaneity": a float 0..1 matching the label,\n'
    '  "evidence": a short verbatim quote from the excerpt supporting your call.'
)


def excerpt(full_text: str, max_words: int) -> str:
    """Head + middle slice, normalized whitespace, capped at max_words.

    Structure (opening statement vs Q&A) is usually evident early, but Q&A can
    start late — so we send the first ~60% from the head and ~40% from the
    middle, labelled, rather than a single head slice.
    """
    words = _WS.sub(" ", full_text or "").strip().split(" ")
    n = len(words)
    if n <= max_words:
        return " ".join(words)
    head_n = int(max_words * 0.6)
    mid_n = max_words - head_n
    head = words[:head_n]
    mid_start = max(head_n, n // 2 - mid_n // 2)
    mid = words[mid_start:mid_start + mid_n]
    return " ".join(head) + "\n[...]\n" + " ".join(mid)


def _spont_value(data: dict | None):
    """Pull the spontaneity score, tolerating key misspellings.

    The 4-bit fine-tuned model occasionally mangles the key (observed:
    'spontivity' instead of 'spontaneity') while otherwise returning correct,
    valid JSON. Rather than discard a good judgment over a typo, accept the
    canonical key first, then any numeric-valued key starting with 'spont'.
    """
    if not data:
        return None
    if data.get("spontaneity") is not None:
        return data["spontaneity"]
    for k, v in data.items():
        if str(k).lower().startswith("spont") and isinstance(v, (int, float, str)):
            return v
    return None


def score_one(llm, row: dict, max_words: int) -> dict | None:
    ex = excerpt(row["full_text"], max_words)
    prompt = USER_TEMPLATE.format(
        title=(row.get("title") or "")[:200],
        etype=row.get("type") or "?",
        excerpt=ex,
    )
    # Defensive against a model returning an empty/garbled completion on a small
    # tail of inputs (observed with gemma, which would degenerate on short
    # ceremony "Exchange With Reporters" remarks and emit nothing). Retry once
    # with a temperature bump to break a deterministic empty; a persistent
    # failure is skipped+logged by the caller. Qwen has not shown this, but the
    # guard is cheap and keeps a batch from being derailed by one bad doc.
    data = llm.json_chat(prompt, system=SYSTEM, max_tokens=MAX_TOKENS)
    if _spont_value(data) is None:
        data = llm.json_chat(prompt, system=SYSTEM, max_tokens=MAX_TOKENS, temperature=0.5)
    raw_score = _spont_value(data)
    if raw_score is None:
        return None
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        return None
    score = max(0.0, min(1.0, score))
    label = str(data.get("label", "")).strip().lower()
    if label not in LABELS:  # derive from score if the model omitted/garbled it
        label = "scripted" if score < 0.35 else "spontaneous" if score >= 0.7 else "mixed"
    return {
        "spontaneity": round(score, 3),
        "label": label,
        "interactive": bool(data.get("interactive")),
        "reason": str(data.get("reason", ""))[:300],
        "evidence": str(data.get("evidence", ""))[:200],
        "excerpt_words": min(len(row["full_text"].split()), max_words),
    }


# --- DB ---------------------------------------------------------------------

def target_dsn(db: str) -> str:
    """Mirror load_to_postgres.target_dsn: libpq defaults unless PG_DSN is set."""
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


def fetch_speeches(conn, types, presidents, only_missing, model, limit,
                   since=None, until=None):
    # presidential_voice excludes non-voice material (third-person WH press
    # releases, written instruments) flagged by scripts/flag_nonvoice.py.
    where = ["is_canonical", "presidential_voice", "full_text IS NOT NULL",
             "word_count >= 200"]
    params: list = []
    if types:
        where.append("type = ANY(%s)")
        params.append(list(types))
    if presidents:
        where.append("president_key = ANY(%s)")
        params.append(list(presidents))
    if since:
        where.append("date >= %s")
        params.append(since)
    if until:
        where.append("date < %s")
        params.append(until)
    if only_missing:
        where.append(
            "id NOT IN (SELECT speech_id FROM llm_extractions "
            "WHERE extraction_type = %s AND prompt_version = %s AND model = %s)"
        )
        params += [EXTRACTION_TYPE, PROMPT_VERSION, model]
    sql = (
        "SELECT id, title, type, word_count, full_text FROM speeches WHERE "
        + " AND ".join(where)
        + " ORDER BY date NULLS LAST, id"
    )
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def write_row(conn, speech_id, model, result):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_extractions "
            "(speech_id, model, prompt_version, extraction_type, "
            " extracted_pattern, confidence_score, raw) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            # idempotent against the unique index on
            # (speech_id, extraction_type, prompt_version, model) — concurrent
            # runs / re-scores can't create duplicate rows.
            "ON CONFLICT (speech_id, extraction_type, prompt_version, model) DO NOTHING",
            (speech_id, model, PROMPT_VERSION, EXTRACTION_TYPE,
             result["label"], result["spontaneity"], json.dumps(result)),
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="presidential_speech")
    ap.add_argument("--model", default=DEFAULT_SPONTANEITY_MODEL,
                    help=f"LM Studio model id (default {DEFAULT_SPONTANEITY_MODEL})")
    ap.add_argument("--types", nargs="*", default=None,
                    help="restrict to these speech types (default: all)")
    ap.add_argument("--presidents", nargs="*", default=None,
                    help="restrict to these president_keys")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="only speeches on/after this date (e.g. Trump 2nd term: 2021-01-20)")
    ap.add_argument("--until", default=None, metavar="YYYY-MM-DD",
                    help="only speeches strictly before this date")
    ap.add_argument("--only-missing", action="store_true",
                    help="skip speeches already scored for this model+prompt_version")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-words", type=int, default=800,
                    help="excerpt cap (head+middle) sent to the model; 800 was the "
                         "sweet spot (same accuracy as 1500, less prompt-eval; 500 broke)")
    ap.add_argument("--sample", type=int, default=None, metavar="N",
                    help="score N random-ish speeches, PRINT only, do not write")
    args = ap.parse_args()

    model = args.model
    llm = get_llm(model=model, timeout=REQUEST_TIMEOUT, max_retries=1)
    if not llm.is_available():
        raise SystemExit(
            "LM Studio not reachable. Start the server / load the model "
            f"({model}); see llm.py --check."
        )
    LOG.info("model=%s prompt_version=%s max_words=%d", model, PROMPT_VERSION, args.max_words)

    sampling = args.sample is not None
    limit = args.sample if sampling else args.limit

    with psycopg.connect(target_dsn(args.db)) as conn:
        rows = fetch_speeches(conn, args.types, args.presidents,
                              args.only_missing and not sampling, model, limit,
                              since=args.since, until=args.until)
        LOG.info("%d transcript(s) to score%s", len(rows),
                 " (SAMPLE — not writing)" if sampling else "")

        t0 = time.time()
        written = skipped = 0
        for i, row in enumerate(rows, 1):
            try:
                result = score_one(llm, row, args.max_words)
            except Exception as e:  # never abort the batch on one bad doc
                LOG.warning("scoring failed for %s: %s", row["id"], e)
                skipped += 1
                continue
            if result is None:
                LOG.warning("empty/unparseable model output for %s (%s) — skipped",
                            row["id"], row["type"])
                skipped += 1
                continue
            if sampling:
                print(f"[{row['type']:<16}] {result['spontaneity']:.2f} "
                      f"{result['label']:<11} wc={row['word_count']:<5} "
                      f"int={int(result['interactive'])}  {row['id']}\n"
                      f"    title : {(row['title'] or '')[:90]}\n"
                      f"    reason: {result['reason']}\n"
                      f"    quote : {result['evidence']}")
            else:
                write_row(conn, row["id"], model, result)
                written += 1
                if written % 25 == 0:
                    conn.commit()
            if i % 25 == 0 or i == len(rows):
                rate = i / max(1e-9, time.time() - t0)
                LOG.info("%d/%d  (%.1f docs/sec)", i, len(rows), rate)
        if not sampling:
            conn.commit()
            dt = time.time() - t0
            LOG.info("wrote %d spontaneity rows, skipped %d (%.0f%%) in %.0fs "
                     "(%.1f docs/sec)", written, skipped,
                     100 * skipped / max(1, written + skipped), dt,
                     written / max(1e-9, dt))
            for line in llm.usage_report().splitlines():   # tokens + commercial-cost estimate
                LOG.info("%s", line)


if __name__ == "__main__":
    main()
