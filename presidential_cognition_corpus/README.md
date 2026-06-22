# Presidential Cognition Corpus

A local research corpus of U.S. presidential speech transcripts (Reagan →
present) built for longitudinal linguistic and cognitive analysis, with extra
depth on Donald Trump (campaign-era 2015 onward) and a comparison set back to
Ronald Reagan.

**This stage is about building the corpus, not drawing conclusions.** The goal
is to assemble, clean, normalize, deduplicate, and metadata-tag a large body of
text (target 1,000 → 20,000 transcripts) so that later analysis — semantic
drift, lexical diversity, sentence complexity, within-president aging, and
cross-president comparison — can run on top of a clean, well-documented base.

Designed to run locally (built/tested for a Mac Mini, 64 GB RAM).

---

## Quick start — no typing

In Finder, open this folder and **double-click**:

1. **`1 — Setup & Test.command`** — sets up everything and runs a small test.
   (First time only: if macOS warns about an unidentified developer, right-click
   the file → **Open** → **Open**.)
2. **`2 — Collect Everything.command`** — runs the full collection. Safe to stop
   and restart; it resumes and never re-downloads what it already has.

Outputs land in `data_clean/metadata.csv`, `data_clean/metadata.parquet`,
`data_clean/speeches/*.txt`, and `logs/collection_report.md`.

### Quick start — command line (optional)

If you prefer the terminal. Type each line on its own; do **not** paste the
`#` explanation lines (zsh, the macOS default shell, does not treat them as
comments).

```bash
cd presidential_cognition_corpus
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-optional.txt
python -m spacy download en_core_web_sm
python -m nltk.downloader cmudict
```

Then, a small smoke test (5 docs per president):

```bash
python scripts/run_pipeline.py --sources app --limit 5
```

Full run:

```bash
python scripts/run_pipeline.py --sources app miller
```

Re-run only post-processing on already-downloaded data:

```bash
python scripts/run_pipeline.py --no-collect
```

---

## Presidents in scope

| key | president | window collected |
|---|---|---|
| `reagan` | Ronald Reagan | 1981-01-20 → 1989-01-20 |
| `bush41` | George H. W. Bush | 1989 → 1993 |
| `clinton` | Bill Clinton | 1993 → 2001 |
| `bush43` | George W. Bush | 2001 → 2009 |
| `obama` | Barack Obama | 2009 → 2017 |
| `trump` | Donald Trump | **2015-06-15** → present (campaign-aware) |
| `biden` | Joe Biden | 2021 → 2025 |

Edit `scripts/common.py` (`PRESIDENTS`) to change windows or matching names.

---

## Sources (priority order)

1. **American Presidency Project** (`collect_app.py`) — backbone: speeches,
   remarks, press conferences, debates, interviews, radio addresses.
2. **Miller Center** (`collect_miller.py`) — smaller, very clean curated set.
3. **Trump White House / NARA archive** (`collect_trump_sources.py --whitehouse trump_archive`)
   — official 2017-2021 transcripts. Also `biden_archive` and `current`.
4. **Current White House** remarks — `--whitehouse current`.
5. **Factba.se / Rev / YouTube** — via **manual drop-folder ingest** (see below),
   because these restrict bulk scraping and/or the public APIs have been removed.

### Manual ingest for rallies / interviews / captions

Drop saved transcripts into `data_raw/factbase/`, `data_raw/rev/`, or
`data_raw/youtube/` as `.txt` or `.html`. Optionally add a sidecar `.json` with
the same basename:

```json
{
  "title": "Rally in Phoenix, Arizona",
  "date": "2020-08-18",
  "president": "trump",
  "source_url": "https://...",
  "event_type": "rally",
  "machine_generated": false,
  "location": "Phoenix, AZ"
}
```

Then:

```bash
python scripts/collect_trump_sources.py --ingest factbase rev youtube
```

Missing fields are inferred where possible (president/date from filename or
text). YouTube captions are auto-flagged machine-generated and given a lower
`quality_score`.

---

## Pipeline stages

```
collect_app / collect_miller / collect_trump_sources   # acquire raw + first-pass clean
        │
        ▼
normalize_text.py        # uniform cleaning rules, whitespace, preserve markers
        │
        ▼
dedupe.py                # URL + text-hash + fuzzy title + MinHash/RapidFuzz clusters
        │
        ▼
classify_event_type.py   # event_type + prepared/impromptu + Q&A + campaign/official
        │
        ▼
compute_metrics.py       # word/sentence stats, readability, TTR, Q/A ratio
        │
        ▼
build_report.py          # logs/collection_report.md (counts by pres/year/source/type)
```

`run_pipeline.py` chains all of these. Every stage is **idempotent and
restartable** — re-running only does new work. No stage aborts the run on a
single failed transcript; failures are logged and skipped.

---

## Cleaning rules

Raw HTML is preserved in `data_raw/<source>/`. Cleaned plain text in
`data_clean/speeches/` follows: remove nav/menus/ads/copyright/boilerplate;
preserve paragraph structure; normalize whitespace; **preserve speaker labels,
applause/laughter/interruption/inaudible markers**; never rewrite wording; store
retrieval date and source URL (in each file's `#` header block).

---

## Filename convention

```
YYYY-MM-DD_president_source_short-title.txt
2019-09-25_trump_app_news-conference-in-new-york.txt
```

---

## Metadata schema

Stored in both `metadata.csv` and `metadata.parquet`:

`id, president, date, year, title, source, source_url, event_type, location,
campaign_or_official, prepared_or_impromptu, has_q_and_a, word_count,
char_count, quality_score, duplicate_cluster_id, is_canonical, raw_file_path,
clean_file_path, notes` — plus Milestone-3 metrics: `sentence_count,
mean_sentence_length, median_sentence_length, paragraph_count, type_token_ratio,
flesch_reading_ease, flesch_kincaid_grade, speaker_label_count, question_count,
question_answer_ratio, event_duration_seconds, retrieval_date`.

`id` is a deterministic hash of `source|url|date`, so re-runs never duplicate
rows. Duplicates are clustered (`duplicate_cluster_id`) with one member flagged
`is_canonical=1` — **nothing is deleted**.

---

## Local LLM (LM Studio)

Intense LLM work runs against a **local** model served by LM Studio's
OpenAI-compatible endpoint — no cloud calls. Configure via env vars:

```bash
export LLM_BASE_URL="http://localhost:1234/v1"
export LLM_MODEL="google/gemma-4-26b-a4b"   # or whatever is loaded in LM Studio
export LLM_API_KEY="lm-studio"              # value ignored by LM Studio
pip install openai

python scripts/llm.py --check               # verify the server + loaded model
python scripts/classify_event_type.py --llm # LLM-assisted classification (opt-in)
```

The core pipeline (collect → clean → dedupe → metrics) is fully deterministic
and LLM-free. The LLM is opt-in and intended for ambiguous classification now
and for the cognition/analysis phase later.

---

## Operational notes

- **robots.txt respected** by default; rate-limited per host; responses cached
  in `.cache/` so re-runs are cheap. `--no-robots` exists but use responsibly.
- All collectors are restartable via `.cache/state_*.json`.
- Be a good citizen: this is academic research use. Check each site's terms;
  prefer the official/archival sources and manual ingest over aggressive
  scraping of sites that disallow it.

---

## What's intentionally NOT here yet

No cognition analysis. The corpus and metrics are scaffolding for later work:
topic half-life, semantic drift, topic-switch frequency, lexical diversity,
sentence complexity, repetition rate, pronoun usage, vocabulary richness,
named-entity density, prepared-vs-impromptu differences, within-president aging,
and cross-president comparison. Put exploratory analysis in `notebooks/`.

---

## Disclaimer

Inferring cognitive change from public speech is methodologically fraught:
speaking style, event type (a rally vs. a written address), audience, transcript
quality, and normal aging all confound any "decline" signal. This corpus is
built to let those confounds be measured and controlled for — not to support
casual diagnosis. Treat results as linguistic description, not clinical
assessment.
