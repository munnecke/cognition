# Handoff notes (for Claude Code or any local dev)

## What this is
A local research corpus of U.S. presidential speech transcripts (Reagan →
present) for later longitudinal linguistic/cognitive analysis. See `README.md`
for the full spec. Build target: 1,000–20,000 transcripts. Python, runs locally.

## Current state (2026-06-21)
The full pipeline is written and **verified end-to-end against the live site**
(35-doc slice: collect → normalize → dedupe → classify → metrics → report; CSV +
Parquet). All three sources — **American Presidency Project**, **Miller Center**, and the
**Trump White House / NARA archive** — are now confirmed working live (see
below). A full **spoken-only** scale-up run is in progress.

### Scope: SPOKEN material only (2026-06-21)
The corpus is for analyzing presidential **speech and tone**, so APP collection
now defaults to spoken categories only (`SPOKEN_CATEGORY_IDS` in `collect_app.py`,
applied via the `category2[]` advanced-search filter). This excludes all written
documents (executive orders, proclamations, memoranda, messages, letters, signing
statements, nominations, pardons, press releases, press-secretary statements).
- Effect on APP: ~112,700 docs (all types) → **~22,500 spoken docs** (~20%), and
  ~66h → **~13h** at the 2s rate limit.
- Default is spoken-only; pass `--all-categories` (collect_app.py or run_pipeline.py)
  to collect everything. Edit `SPOKEN_CATEGORY_IDS` to widen/narrow the whitelist.
- Miller Center is already a curated speeches-only site (no filter needed). The
  Trump NARA archive still includes written statements — NOT yet category-filtered
  (a title-based spoken filter could be added there if its noise matters; APP +
  Miller already cover Trump's spoken material).

### What's confirmed working
- `scripts/common.py` — schema, polite/cached/rate-limited HTTP, state store.
- Person discovery: `collect_app.py` auto-discovers APP person term-ids from the
  advanced-search `<select name="person2">`. All 7 presidents map correctly
  (Reagan 200296, Bush41 200297, Clinton 200298, Bush43 200299, Obama 200300,
  Trump 1st-term 200301 + 2nd-term, Biden 200320). Verify: `--list-people`.
- normalize_text.py / dedupe.py / classify_event_type.py / compute_metrics.py /
  build_report.py — all run end-to-end on synthetic data.

### The bug that was just fixed (verify it holds against the live site)
First real run returned only the empty landing page ("187,868 Records") for
every query. Root cause: `items_per_page=60` is invalid — the form only accepts
{5,10,25,50,100}, and an invalid value makes Drupal drop the query. Fixes
applied in `collect_app.py`:
- `build_results_url`: items_per_page clamped to 100; dates optional.
- `extract_doc_links`: scopes to `div.view-content`, excludes app-categories /
  guidebook / category-attributes nav links.
- multi-id collection per president (Trump's two terms).
- early-stop after 2 empty result pages (so a broken run can't grind for an hour).

### VERIFIED 2026-06-21 against the live site
The diagnostic + a 35-doc validation run (`--sources app --limit 5`, all 7
presidents) confirmed:
- All 3 results-URL variants return real document links (100/100/25). The
  `items_per_page` fix holds.
- Document-page selectors all hit on live pages: `CANDIDATE_TITLE` →
  `div.field-ds-doc-title h1`, `CANDIDATE_DATE` → `span.date-display-single`,
  `CANDIDATE_LOCATION` → `div.field-spot-state`, `CANDIDATE_CONTENT` →
  `div.field-docs-content`.
- Output quality: 35/35 correctly attributed, 0 unknown president, 0 empty date.

Two fixes made during verification (both in `collect_app.py`):
1. **President attribution** — `parse_document()` now reads the explicit speaker
   block (`CANDIDATE_PERSON` → `div.field-docs-person h3.diet-title a`) and
   prefers it over title/body inference. Before, a Reagan doc that *quoted*
   Carter resolved to `None`; body inference was unreliable and could
   misattribute. Body/title remain as fallbacks.
2. **Non-speech index pages** — `_is_real_doc()` now excludes auto-generated
   `*-event-timeline` and `digest-other-white-house-announcements*` slugs
   (`NON_DOC_SLUG_PATTERNS`); they recur per-president and aren't transcripts.

NOTE: the `--limit 5` validation slice (35 rows, incl. the now-filtered timeline/
digest pages collected before the filter) is still in `data_clean/`. Wipe
`data_clean/`, `data_raw/app/`, and `.cache/state_app.json` before a clean
scale-up if you want those excluded retroactively.

### Next: scale up
```
source .venv/bin/activate
python scripts/run_pipeline.py --sources app            # full APP, all presidents
python scripts/run_pipeline.py --sources app miller     # + Miller (selectors UNTESTED live)
```

## Sources beyond APP
- **Miller Center: VERIFIED live 2026-06-21** (`collect_miller.py`). Listing crawl
  works (1,059 speeches across 34 pages); out-of-scope pre-Reagan speakers are
  correctly skipped; 5-doc validation slice ran clean through the full pipeline.
  Fixes made during verification:
  - **President attribution** — `parse_speech()` now reads the explicit speaker
    block (`CANDIDATE_PERSON` → `p.president-name`) and prefers it over title/body.
    Before, Trump's 2025 inaugural resolved to `clinton` (former presidents seated
    on the dais get name-matched in the transcript body).
  - `CANDIDATE_TITLE` now leads with `h2.presidential-speeches--title` (the real
    title element) instead of falling through to a bare `h1`.
  - `crawl_listing()` no longer emits intra-page duplicate URLs.
  - NOTE: scope is determined *after* fetching each speech page, so a full run
    fetches all ~1,059 pages to keep the ~in-scope subset (Reagan→present).
- **Trump White House / NARA: VERIFIED live 2026-06-21** (`collect_trump_sources.py`).
  - Engine (A) archive crawler: `trumpwhitehouse.archives.gov` listing + post
    parsing work; 5-doc crawl slice succeeded (title `h1`, date `time`, content
    `div.page-content`).
  - Engine (B) drop-folder ingest: verified with a synthetic factbase file +
    JSON sidecar (metadata, event_type, location, quality score all applied),
    then removed.
  - Fixes made during verification:
    - **Operator-precedence bug** in `crawl_whitehouse` link filter — `not in seen`
      only applied to the `/briefing` branch, so `/news` + `/remarks` URLs (the
      `current` target) could duplicate. Now grouped correctly.
    - **President attribution** — these archives are single-administration, so
      `WHITEHOUSE_TARGETS` now carries a `default_president` (trump/biden/trump)
      used as the fallback when a post never names the president. Before, short
      releases/letters landed as `unknown` (2 of the 5-doc slice).
  - Manual-ingest drop folders (`data_raw/factbase|rev|youtube/`) are empty —
    that path only does work when you drop files in (see README pairing rules).

## NLP feature layer (2026-06-21)
`scripts/extract_features.py` — deterministic, LLM-free NLP features for the
longitudinal cognition analysis. Writes a SEPARATE table
`data_clean/linguistic_features.csv` (+ `.parquet`) keyed by speech `id`, so the
canonical `METADATA_FIELDS` schema stays lean and the feature set maps 1:1 to a
future Postgres `linguistic_features` table.
- Backbone: **spaCy** (`en_core_web_sm`, tagger+parser+morph+lemmatizer) +
  length-robust lexical diversity (**MTLD**, **MATTR** — these replace raw TTR,
  which is length-confounded and would manufacture false trends) + **VADER**
  rule-based sentiment.
- Features: POS ratios (incl. 1st-person **singular vs plural**, `i_to_we_ratio`),
  dependency-based syntactic complexity (mean dependency distance, tree depth,
  subordination, clauses/sentence), lexical diversity, Berisha/Pennebaker-style
  cognition markers (indefinite-noun / hedge / filler rates). Each row carries
  `spacy_model` + `extractor_version` provenance.
- Run: `python scripts/extract_features.py [--only-missing] [--limit N]`, or add
  `--features` to `run_pipeline.py`. Deterministic & restartable.
- Division of labor: NLP here = reproducible backbone (`linguistic_features`);
  the LLM layer = interpretive signals (`llm_extractions`), kept separate so a
  model-version change can't move the longitudinal trend lines.
- Deps installed this session: `python -m spacy download en_core_web_sm` and the
  NLTK `vader_lexicon`. (spaCy had no model before — `compute_metrics.py` was
  silently falling back to a blank sentencizer.)

### Storage + browser (BUILT 2026-06-22)
- `scripts/load_to_postgres.py` — idempotent load of the flat files into Postgres
  DB `presidential_speech` (PG 18.3, pgvector/pg_trgm available). Keyed on speech
  `id`; re-runnable as the corpus grows. Tables: `presidents`, `speeches`
  (+ full_text + tsvector FTS), `linguistic_features` (promoted numeric cols +
  `features` JSONB), `llm_extractions` (model+prompt provenance; empty until the
  LLM layer runs). Flat files remain the source of truth.
- **Web GUIs query Postgres DIRECTLY — no mirror, no sync (2026-06-22).**
  `scripts/serve_gui.sh` starts both:
  - **marimo dashboard** (`scripts/dashboard.py`) → http://localhost:2718. The
    primary GUI. Reactive Python app served read-only; queries Postgres live and
    REUSES our own code (the Berisha validation panel calls `replicate_berisha`).
    The dashboard is a `.py` file in the repo — no separate app-database to manage.
  - **pgweb** → http://localhost:8081. Lightweight read-only table browser + SQL
    runner, directly on Postgres.
- Datasette path RETIRED (it required a duplicate SQLite mirror). The scripts
  remain as an optional lightweight alternative: `scripts/build_browser.sh` +
  `scripts/datasette_metadata.yaml` rebuild a SQLite mirror and serve it at :8001.
  Not used by default.
- NOTE: `speeches.type` is populated by the `classify_event_type` pipeline stage,
  which runs after collection — so it's null mid-collection and fills in on the
  full post-processing pass. Re-run `build_browser.sh` after the scrape completes
  for the full ~22k-doc enriched browser.

### Method validation (BUILT 2026-06-22)
- `scripts/segment_speaker.py` — president-only spontaneous-answer segmentation
  (drops prepared statements, questions, topic headers, [brackets]).
- `scripts/replicate_berisha.py` — reproduces Berisha et al. 2015 as an
  end-to-end validation. **Reagan replicates cleanly (3/3 verdicts match)**;
  Bush control mostly matches (pending his full collection). See
  `documents/tech_journal.md` for results + code, and `documents/nihms-1062581.pdf`
  for the paper.

### Future (discussed, not built)
`speech_embeddings` (pgvector) for semantic drift / clustering; knowledge-graph
entity/relation tables (spaCy NER), optionally cross-linked to the `curator` DB.

## Local LLM
`scripts/llm.py` targets LM Studio (OpenAI-compatible, default
`http://localhost:1234/v1`, model `google/gemma-4-26b-a4b`, env-overridable).
The core pipeline is LLM-free; `classify_event_type.py --llm` is opt-in.
LLM is intended for the later analysis phase.

## Operational rules (please keep)
- Respect robots.txt + rate limits (already implemented in `PoliteSession`).
- Never delete duplicates — cluster them (`duplicate_cluster_id`) and mark one
  `is_canonical`. Preserve raw HTML in `data_raw/`.
- Never abort the whole run on one bad transcript — log and continue.
- Restartable: HTTP cache in `.cache/http`, per-collector state in
  `.cache/state_*.json`.

## Layout
```
scripts/   common.py, collect_app.py, collect_miller.py, collect_trump_sources.py,
           normalize_text.py, dedupe.py, classify_event_type.py, compute_metrics.py,
           build_report.py, run_pipeline.py, llm.py
data_raw/  per-source raw HTML (+ _diag/ from the diagnostic)
data_clean/ speeches/*.txt, metadata.csv, metadata.parquet
logs/      per-stage logs + collection_report.md
```
