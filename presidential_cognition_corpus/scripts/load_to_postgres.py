"""
load_to_postgres.py — load the flat-file corpus into PostgreSQL.

The collection pipeline keeps the durable source of truth as flat files
(data_clean/metadata.csv, the clean .txt speeches, linguistic_features.csv).
This stage loads them into a queryable Postgres database WITHOUT coupling the
scraper to the DB: it is idempotent (re-runnable as the corpus grows) and keyed
on the deterministic speech `id`, so re-loads upsert cleanly.

Schema
------
  presidents          one row per president (from common.PRESIDENTS)
  speeches            one row per transcript; carries full_text + a tsvector for
                      full-text search; FK -> presidents
  linguistic_features 1:1 with speeches; promoted numeric columns for querying +
                      a `features` JSONB holding the full extractor row + provenance
  llm_extractions     1:many with speeches; provenance (model, prompt_version);
                      empty until the LLM analysis layer runs

Connection: libpq defaults (local socket) unless PG_DSN is set. Target DB name
via --db (default: presidential_speech); created if absent.

Usage:  python load_to_postgres.py [--db presidential_speech]
"""

from __future__ import annotations

import argparse
import json
import os

import psycopg

import common as C

LOG = C.get_logger("load_to_postgres")

ADMIN_DSN = os.environ.get("PG_DSN", "dbname=postgres")

SCHEMA = """
CREATE TABLE IF NOT EXISTS presidents (
    id          serial PRIMARY KEY,
    key         text UNIQUE NOT NULL,
    name        text NOT NULL,
    term_start  date,
    term_end    date
);

CREATE TABLE IF NOT EXISTS speeches (
    id                   text PRIMARY KEY,
    president_id         int REFERENCES presidents(id),
    president_key        text,
    date                 date,
    year                 int,
    title                text,
    type                 text,
    location             text,
    source               text,
    source_url           text,
    word_count           int,
    quality_score        real,
    duplicate_cluster_id text,
    is_canonical         boolean,
    campaign_or_official text,
    full_text            text,
    tsv                  tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(full_text, ''))) STORED,
    retrieval_date       date
);
CREATE INDEX IF NOT EXISTS speeches_pres_date_idx ON speeches (president_id, date);
CREATE INDEX IF NOT EXISTS speeches_tsv_idx ON speeches USING gin (tsv);
CREATE INDEX IF NOT EXISTS speeches_type_idx ON speeches (type);

CREATE TABLE IF NOT EXISTS linguistic_features (
    speech_id                   text PRIMARY KEY REFERENCES speeches(id) ON DELETE CASCADE,
    n_words                     int,
    mtld                        real,
    mattr_50                    real,
    type_token_ratio            real,
    first_person_singular_ratio real,
    first_person_plural_ratio   real,
    i_to_we_ratio               real,
    mean_dependency_distance    real,
    subordination_ratio         real,
    indefinite_noun_ratio       real,
    hedge_ratio                 real,
    vader_compound              real,
    spacy_model                 text,
    extractor_version           text,
    features                    jsonb DEFAULT '{}'   -- full extractor row (future-proof)
);

CREATE TABLE IF NOT EXISTS llm_extractions (
    id              bigserial PRIMARY KEY,
    speech_id       text REFERENCES speeches(id) ON DELETE CASCADE,
    model           text NOT NULL,
    prompt_version  text NOT NULL,
    extraction_type text,
    extracted_pattern text,
    confidence_score real,
    raw             jsonb,
    created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS llm_extractions_speech_idx ON llm_extractions (speech_id);
"""

# Promoted feature columns mirrored from linguistic_features.csv (rest -> JSONB).
PROMOTED = ["n_words", "mtld", "mattr_50", "type_token_ratio",
            "first_person_singular_ratio", "first_person_plural_ratio",
            "i_to_we_ratio", "mean_dependency_distance", "subordination_ratio",
            "indefinite_noun_ratio", "hedge_ratio", "vader_compound",
            "spacy_model", "extractor_version"]


def _num(v):
    """Empty string / missing -> None; else the raw value for psycopg to cast."""
    if v is None:
        return None
    v = str(v).strip()
    return v if v else None


def _bool(v):
    v = (str(v).strip() if v is not None else "")
    if v in ("1", "true", "True", "yes"):
        return True
    if v in ("0", "false", "False", "no"):
        return False
    return None


def ensure_database(db: str) -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db}"')
            LOG.info("Created database %s.", db)
        else:
            LOG.info("Database %s already exists.", db)


def target_dsn(db: str) -> str:
    # Reuse PG_DSN host/user settings if provided, swapping the dbname.
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


def _read_body(rel: str) -> str:
    path = C.ROOT / rel
    if not rel or not path.exists():
        return ""
    return "\n".join(l for l in path.read_text(encoding="utf-8", errors="replace").split("\n")
                     if not l.startswith("#")).strip()


def load(db: str) -> None:
    import pandas as pd

    ensure_database(db)
    meta = C.load_metadata()
    if meta.empty:
        LOG.warning("metadata.csv is empty; nothing to load.")
        return

    feats = {}
    fpath = C.DATA_CLEAN / "linguistic_features.csv"
    if fpath.exists():
        fdf = pd.read_csv(fpath, dtype=str, keep_default_na=False)
        feats = {r["id"]: dict(r) for _, r in fdf.iterrows()}

    with psycopg.connect(target_dsn(db)) as conn:
        conn.execute(SCHEMA)

        # presidents (from the single source of truth in common.py)
        with conn.cursor() as cur:
            for p in C.PRESIDENTS:
                cur.execute(
                    """INSERT INTO presidents (key, name, term_start, term_end)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (key) DO UPDATE SET
                         name = EXCLUDED.name, term_start = EXCLUDED.term_start,
                         term_end = EXCLUDED.term_end""",
                    (p.key, p.display, p.collect_from, p.collect_to))
            pres_ids = dict(cur.execute("SELECT key, id FROM presidents").fetchall())

        # speeches
        n_sp = 0
        with conn.cursor() as cur:
            for _, r in meta.iterrows():
                sid = (r.get("id") or "").strip()
                if not sid:
                    continue
                pkey = (r.get("president") or "").strip()
                cur.execute(
                    """INSERT INTO speeches
                       (id, president_id, president_key, date, year, title, type,
                        location, source, source_url, word_count, quality_score,
                        duplicate_cluster_id, is_canonical, campaign_or_official,
                        full_text, retrieval_date)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         president_id=EXCLUDED.president_id, president_key=EXCLUDED.president_key,
                         date=EXCLUDED.date, year=EXCLUDED.year, title=EXCLUDED.title,
                         type=EXCLUDED.type, location=EXCLUDED.location, source=EXCLUDED.source,
                         source_url=EXCLUDED.source_url, word_count=EXCLUDED.word_count,
                         quality_score=EXCLUDED.quality_score,
                         duplicate_cluster_id=EXCLUDED.duplicate_cluster_id,
                         is_canonical=EXCLUDED.is_canonical,
                         campaign_or_official=EXCLUDED.campaign_or_official,
                         full_text=EXCLUDED.full_text, retrieval_date=EXCLUDED.retrieval_date""",
                    (sid, pres_ids.get(pkey), pkey or None, _num(r.get("date")),
                     _num(r.get("year")), r.get("title") or None, r.get("event_type") or None,
                     r.get("location") or None, r.get("source") or None,
                     r.get("source_url") or None, _num(r.get("word_count")),
                     _num(r.get("quality_score")), r.get("duplicate_cluster_id") or None,
                     _bool(r.get("is_canonical")), r.get("campaign_or_official") or None,
                     _read_body(r.get("clean_file_path", "")), _num(r.get("retrieval_date"))))
                n_sp += 1

                # linguistic features (if present for this speech)
                f = feats.get(sid)
                if f:
                    promoted = [_num(f.get(c)) for c in PROMOTED]
                    cur.execute(
                        f"""INSERT INTO linguistic_features
                            (speech_id, {", ".join(PROMOTED)}, features)
                            VALUES (%s, {", ".join(["%s"] * len(PROMOTED))}, %s)
                            ON CONFLICT (speech_id) DO UPDATE SET
                            {", ".join(f"{c}=EXCLUDED.{c}" for c in PROMOTED)},
                            features=EXCLUDED.features""",
                        [sid, *promoted, json.dumps(f)])
            conn.commit()

        counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in ("presidents", "speeches", "linguistic_features", "llm_extractions")}
    LOG.info("Loaded into %s: %s", db, counts)


def main():
    ap = argparse.ArgumentParser(description="Load the corpus flat files into PostgreSQL.")
    ap.add_argument("--db", default="presidential_speech", help="target database name")
    args = ap.parse_args()
    load(args.db)


if __name__ == "__main__":
    main()
