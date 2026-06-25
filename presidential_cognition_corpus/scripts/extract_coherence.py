"""
extract_coherence.py — semantic-coherence ('half-life of a thought') features.

Deterministic, embedding-based layer (bge-m3 via LM Studio) measuring topic
maintenance / distractibility — the speech-coherence literature (Bedi 2015,
Elvevåg 2007) applied to presidential Q&A. Writes the `speech_coherence` table
(parallel to linguistic_features; reproducible, model-versioned). See
documents/coherence_layer_plan.md.

Per transcript (president answers only, segmented into turns via qa_pairs so the
measure is WITHIN a sustained answer, not across the interview's turn-taking):
  local_coherence   mean cosine of ADJACENT sentences within an answer (lag 1)
  global_coherence  mean cosine of each sentence to its answer's centroid
  half_life         sentence lag at which within-answer similarity falls halfway
                    from its lag-1 value to the answer's long-range baseline
                    (pooled across answers for stability) — short = drifts fast
  qa_relevance      mean cosine(question, answer) — did answers engage questions?
                    (deterministic cousin of the LLM 'evasiveness' dimension)

Anisotropy fix: raw cosine on these embeddings is compressed (~0.48 baseline), so
we subtract a GLOBAL mean sentence vector (computed once from a corpus sample,
cached) before cosine — the standard 'all-but-the-mean' de-biasing that opens the
dynamic range.

Usage:  python scripts/extract_coherence.py [--only-missing] [--limit N]
                 [--min-spont 0.5] [--sample ID ...]
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import psycopg
import spacy

import common as C
import qa_pairs as QA
from llm import DEFAULT_BASE_URL

EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-bge-m3")
EXTRACTOR_VERSION = "coherence-v1"
MEAN_CACHE = C.CACHE / f"coherence_mean_{EMBED_MODEL.replace('/', '_')}.npy"
_MIN_SENTS = 4          # an answer needs this many sentences to contribute decay/global
_MAX_LAG = 15

_senter = spacy.blank("en")
_senter.add_pipe("sentencizer")   # rule-based: fast, fine on clean transcripts


def _client():
    from openai import OpenAI
    return OpenAI(base_url=DEFAULT_BASE_URL, api_key="lm-studio", timeout=120, max_retries=2)


def embed_raw(client, texts: list[str]) -> np.ndarray:
    out = []
    for i in range(0, len(texts), 64):
        r = client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 64])
        out.extend(d.embedding for d in r.data)
    return np.asarray(out, dtype=np.float32)


def sentences(text: str) -> list[str]:
    return [s.text.strip() for s in _senter(text).sents if len(s.text.split()) >= 4]


# --- global mean (anisotropy de-biasing), computed once and cached --------------

def load_or_build_mean(conn, client) -> np.ndarray:
    if MEAN_CACHE.exists():
        return np.load(MEAN_CACHE)
    C.CACHE.mkdir(parents=True, exist_ok=True)
    with conn.cursor() as cur:
        cur.execute("SELECT full_text FROM speeches WHERE is_canonical AND presidential_voice "
                    "AND word_count >= 400 ORDER BY md5(id) LIMIT 250")
        sample = []
        for (body,) in cur.fetchall():
            for _, a in QA.qa_pairs(body or ""):
                sample.extend(sentences(a))
            if len(sample) >= 4000:
                break
    sample = sample[:4000]
    E = embed_raw(client, sample)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    mu = E.mean(axis=0)
    np.save(MEAN_CACHE, mu)
    return mu


def center_normalize(E: np.ndarray, mu: np.ndarray) -> np.ndarray:
    E = E - mu
    n = np.linalg.norm(E, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return E / n


# --- per-document coherence -----------------------------------------------------

def coherence_for_doc(body: str, client, mu) -> dict | None:
    pairs = QA.qa_pairs(body or "")
    if not pairs:
        return None
    answers = [a for _, a in pairs]
    questions = [q for q, _ in pairs]

    # sentence-level: embed all answer sentences in one batch, keep per-answer spans
    spans, sents = [], []
    for a in answers:
        s = sentences(a)
        spans.append((len(sents), len(sents) + len(s)))
        sents.extend(s)
    if len(sents) < _MIN_SENTS:
        return None
    SE = center_normalize(embed_raw(client, sents), mu)

    local, glob = [], []
    lag_sum = np.zeros(_MAX_LAG + 1)
    lag_cnt = np.zeros(_MAX_LAG + 1)
    n_answers_used = 0
    for lo, hi in spans:
        if hi - lo < 2:
            continue
        A = SE[lo:hi]
        sims = A @ A.T
        if hi - lo >= _MIN_SENTS:
            n_answers_used += 1
            glob.extend(A @ (A.mean(0) / (np.linalg.norm(A.mean(0)) or 1)))
        for k in range(1, min(_MAX_LAG, hi - lo - 1) + 1):
            d = np.diagonal(sims, offset=k)
            lag_sum[k] += d.sum(); lag_cnt[k] += d.size
        local.append(np.diagonal(sims, offset=1).mean())

    curve = np.array([lag_sum[k] / lag_cnt[k] for k in range(1, _MAX_LAG + 1)
                      if lag_cnt[k] > 0])
    half_life = _half_life(curve) if len(curve) >= 4 else None

    # Q->A relevance: full-question vs full-answer embeddings
    QE = center_normalize(embed_raw(client, questions + answers), mu)
    nq = len(questions)
    qa_rel = float(np.mean([QE[i] @ QE[nq + i] for i in range(nq)]))

    return {
        "n_pairs": len(pairs), "n_sentences": len(sents), "n_answers_used": n_answers_used,
        "local_coherence": round(float(np.mean(local)), 4) if local else None,
        "global_coherence": round(float(np.mean(glob)), 4) if glob else None,
        "half_life": round(float(half_life), 2) if half_life is not None else None,
        "qa_relevance": round(qa_rel, 4),
    }


def _half_life(curve: np.ndarray):
    s1 = curve[0]
    base = curve[-max(3, len(curve) // 4):].mean()
    if s1 <= base:
        return float("nan")
    target = base + (s1 - base) / 2.0
    for k, v in enumerate(curve, start=1):
        if v <= target:
            return k
    return float(len(curve))


# --- DB / driver ----------------------------------------------------------------

def target_dsn(db):
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


DDL = """
CREATE TABLE IF NOT EXISTS speech_coherence (
    speech_id        text PRIMARY KEY REFERENCES speeches(id) ON DELETE CASCADE,
    embed_model      text NOT NULL,
    extractor_version text NOT NULL,
    n_pairs          integer,
    n_sentences      integer,
    n_answers_used   integer,
    local_coherence  real,
    global_coherence real,
    half_life        real,
    qa_relevance     real,
    created_at       timestamptz DEFAULT now()
);
"""


def write_row(conn, sid, r):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO speech_coherence (speech_id, embed_model, extractor_version, "
            " n_pairs, n_sentences, n_answers_used, local_coherence, global_coherence, "
            " half_life, qa_relevance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (speech_id) DO UPDATE SET "
            " embed_model=EXCLUDED.embed_model, extractor_version=EXCLUDED.extractor_version, "
            " n_pairs=EXCLUDED.n_pairs, n_sentences=EXCLUDED.n_sentences, "
            " n_answers_used=EXCLUDED.n_answers_used, local_coherence=EXCLUDED.local_coherence, "
            " global_coherence=EXCLUDED.global_coherence, half_life=EXCLUDED.half_life, "
            " qa_relevance=EXCLUDED.qa_relevance, created_at=now()",
            (sid, EMBED_MODEL, EXTRACTOR_VERSION, r["n_pairs"], r["n_sentences"],
             r["n_answers_used"], r["local_coherence"], r["global_coherence"],
             r["half_life"], r["qa_relevance"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="presidential_speech")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--min-spont", type=float, default=0.5,
                    help="restrict to the impromptu set (spontaneity >= this)")
    ap.add_argument("--sample", nargs="*", help="score specific speech ids, PRINT only")
    args = ap.parse_args()

    log = C.get_logger("coherence")
    client = _client()
    with psycopg.connect(target_dsn(args.db)) as conn:
        conn.execute(DDL); conn.commit()
        mu = load_or_build_mean(conn, client)
        log.info("global-mean centering vector ready (%s)", MEAN_CACHE.name)

        if args.sample:
            with conn.cursor() as cur:
                cur.execute("SELECT id, president_key, full_text FROM speeches WHERE id = ANY(%s)",
                            (args.sample,))
                rows = cur.fetchall()
            for sid, pk, body in rows:
                r = coherence_for_doc(body, client, mu)
                print(f"{pk:8} {sid}: {r}")
            return

        where = ["s.is_canonical", "s.presidential_voice", "s.word_count >= 200",
                 "e.confidence_score >= %s"]
        params = [args.min_spont]
        if args.only_missing:
            where.append("NOT EXISTS (SELECT 1 FROM speech_coherence c WHERE c.speech_id = s.id)")
        sql = ("SELECT s.id, s.full_text FROM speeches s JOIN llm_extractions e "
               "ON e.speech_id=s.id AND e.extraction_type='spontaneity' "
               "AND e.prompt_version='spontaneity-v2' WHERE " + " AND ".join(where)
               + " ORDER BY s.date, s.id")
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        with conn.cursor() as cur:
            cur.execute(sql, params); todo = cur.fetchall()
        log.info("%d transcript(s) to process", len(todo))

        import time
        t0 = time.time(); written = skipped = 0
        for i, (sid, body) in enumerate(todo, 1):
            try:
                r = coherence_for_doc(body, client, mu)
            except Exception as e:
                log.warning("failed %s: %s", sid, e); skipped += 1; continue
            if r is None:
                skipped += 1; continue
            write_row(conn, sid, r); written += 1
            if written % 50 == 0:
                conn.commit()
            if i % 50 == 0 or i == len(todo):
                log.info("%d/%d (%.1f doc/s)", i, len(todo), i / max(1e-9, time.time() - t0))
        conn.commit()
        log.info("wrote %d, skipped %d", written, skipped)


if __name__ == "__main__":
    main()
