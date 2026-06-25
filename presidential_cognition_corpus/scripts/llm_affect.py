"""
llm_affect.py — LLM-scored affect of the president's spontaneous speech.

The interpretive affect layer (kept in `llm_extractions`, separate from the
deterministic features). Scores four dimensions per transcript, one LLM call,
one row per dimension:

  anger                hostility / attacks / contempt directed outward
  empathy              warmth, compassion, concern for others' hardship
  evasiveness          does the president dodge the question rather than answer?
  emotional_intensity  overall arousal / heat, regardless of valence

Design choices (see documents/tech_journal.md):
  * INPUT is reporter-question + president-answer PAIRS (qa_pairs). Anger / empathy
    / intensity are judged from the president's answers; evasiveness needs the
    question beside the answer (a non-answer is only visible against what was
    asked). Falls back to president-only answers when a transcript has no Q&A
    (evasiveness then returns null and is skipped).
  * BLIND to identity — the title/name is NOT put in the prompt, per the project's
    coded-first de-biasing (affect is where political priors leak most).
  * Model: the validated Qwen2.5-7B-Instruct (same as the spontaneity classifier).
  * Complements VADER (deterministic valence) with signals VADER can't see:
    anger-vs-generic-negativity, evasiveness (discourse-pragmatic), arousal.

Storage: rows in `llm_extractions` keyed (speech_id, extraction_type=<dimension>,
prompt_version='affect-v1', model). Idempotent via the unique index + ON CONFLICT.

Usage:
    python llm_affect.py --sample 6                 # eyeball, no writes
    python llm_affect.py --only-missing --min-spont 0.5   # the impromptu set
"""

from __future__ import annotations

import argparse
import json
import os
import time

import psycopg

import common as C
import qa_pairs as QA
import segment_speaker as S
from llm import get_llm

LOG = C.get_logger("affect")

DEFAULT_AFFECT_MODEL = os.environ.get(
    "LLM_MODEL", "josiefied-qwen2.5-7b-instruct-abliterated-v2-4-bit")
PROMPT_VERSION = "affect-v1"
DIMENSIONS = ("anger", "empathy", "evasiveness", "emotional_intensity")
SENTINEL = "anger"          # dimension used for the --only-missing check
MAX_TOKENS = 400
REQUEST_TIMEOUT = 90.0

SYSTEM = (
    "You are a linguist rating the emotional AFFECT in a U.S. president's "
    "spontaneous speech. You are shown reporter questions (Q) and the "
    "president's answers (A). Judge ONLY the president's own words (the A "
    "turns); ignore the reporters except as the thing being answered.\n\n"
    "Rate each dimension from 0.0 (none) to 1.0 (extreme):\n"
    "  anger — hostility, attacks, contempt, indignation aimed outward (at "
    "opponents, the press, other countries). Not mere disagreement.\n"
    "  empathy — warmth, compassion, acknowledgment of others' hardship, "
    "consolation, concern for people's suffering.\n"
    "  evasiveness — does the president DODGE the questions (deflect, change the "
    "subject, answer a different question, refuse) rather than actually answer? "
    "0 = answers directly; 1 = consistently evades. Judge against the Q turns.\n"
    "  emotional_intensity — overall emotional arousal / heat, regardless of "
    "whether positive or negative. 0 = flat, measured; 1 = highly charged.\n\n"
    "Base each score on the actual words; do not infer from who the speaker is."
)

USER_TEMPLATE = (
    "--- transcript excerpt: reporter questions (Q) and the president's answers (A) ---\n"
    "{excerpt}\n"
    "--- end excerpt ---\n\n"
    "Return ONLY a JSON object, each value an object with a 0..1 score and a "
    "short verbatim quote as evidence:\n"
    '{{"anger": {{"score": <0..1>, "evidence": "..."}}, '
    '"empathy": {{"score": <0..1>, "evidence": "..."}}, '
    '"evasiveness": {{"score": <0..1>, "evidence": "..."}}, '
    '"emotional_intensity": {{"score": <0..1>, "evidence": "..."}}}}'
)


import re
_PARA = re.compile(r"\n\s*\n")


def _president_speech(body: str) -> str:
    """ALL of the president's spoken words (not just answers-to-questions).

    Unlike segment_speaker.president_answers (Berisha: drops the opening
    statement, requires a preceding question), affect needs the president's full
    spontaneous voice — including rally monologues and prepared-then-extempore
    remarks. Keeps president-labelled turns; for a transcript with no speaker
    labels at all (a rally / address), the whole body IS the president."""
    state, kept, saw_label = None, [], False
    for p in _PARA.split(body or ""):
        p = p.strip()
        if not p:
            continue
        if S._QUESTION.match(p):
            state, saw_label = "other", True
            continue
        m = S._PRES.match(p)
        if m:
            state, saw_label = "pres", True
            kept.append(p[m.end():])
            continue
        if S._OTHER_LABEL.match(p):
            state, saw_label = "other", True
            continue
        if S._is_topic_header(p):
            continue
        if state == "pres":
            kept.append(p)
    text = " ".join(kept) if (saw_label and kept) else (body or "")
    return S._WS.sub(" ", S._BRACKET.sub(" ", text)).strip()


def build_excerpt(body: str, max_words: int) -> tuple[str, bool]:
    """Q/A excerpt from qa_pairs, capped. Returns (text, had_pairs).

    For Q&A transcripts, pairs let the model judge evasiveness (answer vs
    question). For non-Q&A spontaneous speech (rallies, addresses), fall back to
    the president's full monologue — evasiveness can't be judged and is dropped."""
    pairs = QA.qa_pairs(body or "")
    if pairs:
        parts, n = [], 0
        for q, a in pairs:
            seg = f"Q: {q}\nA: {a}"
            parts.append(seg)
            n += len(seg.split())
            if n >= max_words:
                break
        return "\n\n".join(parts), True
    return "A: " + " ".join(_president_speech(body).split()[:max_words]), False


def _val(d):
    """Coerce a dimension entry to (score, evidence)."""
    if isinstance(d, dict):
        s = d.get("score")
        ev = str(d.get("evidence", ""))[:200]
    else:
        s, ev = d, ""
    try:
        return max(0.0, min(1.0, float(s))), ev
    except (TypeError, ValueError):
        return None, ev


def _bucket(score: float) -> str:
    return "low" if score < 0.34 else "high" if score >= 0.67 else "moderate"


def score_one(llm, body: str, max_words: int) -> dict | None:
    excerpt, had_pairs = build_excerpt(body, max_words)
    if len(excerpt.split()) < 30:
        return None
    prompt = USER_TEMPLATE.format(excerpt=excerpt)
    data = llm.json_chat(prompt, system=SYSTEM, max_tokens=MAX_TOKENS)
    if not data or "anger" not in data:
        data = llm.json_chat(prompt, system=SYSTEM, max_tokens=MAX_TOKENS, temperature=0.5)
    if not data:
        return None
    out = {}
    for dim in DIMENSIONS:
        if dim == "evasiveness" and not had_pairs:
            continue                       # no questions -> can't judge evasion
        score, ev = _val(data.get(dim))
        if score is None:
            continue
        out[dim] = {"score": round(score, 3), "evidence": ev}
    return out or None


# --- DB ---------------------------------------------------------------------

def target_dsn(db: str) -> str:
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


def fetch(conn, only_missing, min_spont, presidents, limit, model):
    where = ["s.is_canonical", "s.presidential_voice", "s.word_count >= 200",
             "e.extraction_type='spontaneity'", "e.prompt_version='spontaneity-v2'",
             "e.confidence_score >= %s"]
    params = [min_spont]
    if presidents:
        where.append("s.president_key = ANY(%s)")
        params.append(list(presidents))
    if only_missing:
        where.append("NOT EXISTS (SELECT 1 FROM llm_extractions a WHERE a.speech_id=s.id "
                     "AND a.extraction_type=%s AND a.prompt_version=%s AND a.model=%s)")
        params += [SENTINEL, PROMPT_VERSION, model]
    sql = ("SELECT s.id, s.full_text FROM speeches s JOIN llm_extractions e "
           "ON e.speech_id=s.id WHERE " + " AND ".join(where) + " ORDER BY s.date, s.id")
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def write_rows(conn, sid, model, result):
    with conn.cursor() as cur:
        for dim, v in result.items():
            cur.execute(
                "INSERT INTO llm_extractions (speech_id, model, prompt_version, "
                " extraction_type, extracted_pattern, confidence_score, raw) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (speech_id, extraction_type, prompt_version, model) DO NOTHING",
                (sid, model, PROMPT_VERSION, dim, _bucket(v["score"]),
                 v["score"], json.dumps(v)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="presidential_speech")
    ap.add_argument("--model", default=DEFAULT_AFFECT_MODEL)
    ap.add_argument("--min-spont", type=float, default=0.5,
                    help="restrict to the impromptu set (spontaneity >= this)")
    ap.add_argument("--presidents", nargs="*", default=None)
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-words", type=int, default=900)
    ap.add_argument("--sample", type=int, metavar="N", help="print N, do not write")
    args = ap.parse_args()

    model = args.model
    llm = get_llm(model=model, timeout=REQUEST_TIMEOUT, max_retries=1)
    if not llm.is_available():
        raise SystemExit(f"LM Studio not reachable / model not loaded ({model}).")
    LOG.info("model=%s prompt_version=%s", model, PROMPT_VERSION)

    sampling = args.sample is not None
    limit = args.sample if sampling else args.limit
    with psycopg.connect(target_dsn(args.db)) as conn:
        rows = fetch(conn, args.only_missing and not sampling, args.min_spont,
                     args.presidents, limit, model)
        LOG.info("%d transcript(s) to score%s", len(rows),
                 " (SAMPLE — not writing)" if sampling else "")
        t0 = time.time(); written = skipped = 0
        for i, (sid, body) in enumerate(rows, 1):
            try:
                res = score_one(llm, body, args.max_words)
            except Exception as e:
                LOG.warning("failed %s: %s", sid, e); skipped += 1; continue
            if not res:
                skipped += 1; continue
            if sampling:
                print(sid, {k: v["score"] for k, v in res.items()})
            else:
                write_rows(conn, sid, model, res); written += 1
                if written % 25 == 0:
                    conn.commit()
            if i % 25 == 0 or i == len(rows):
                LOG.info("%d/%d (%.1f doc/s)", i, len(rows), i / max(1e-9, time.time() - t0))
        if not sampling:
            conn.commit()
            LOG.info("wrote affect for %d docs, skipped %d", written, skipped)
            for line in llm.usage_report().splitlines():
                LOG.info("%s", line)


if __name__ == "__main__":
    main()
