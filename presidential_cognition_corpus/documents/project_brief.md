# Presidential Cognition Corpus — project brief

*A self-contained briefing you can read, share, or paste into an AI assistant to
explore the project. The code is public at https://github.com/munnecke/cognition
(main project under `presidential_cognition_corpus/`; software only — collected
transcripts are kept local, not committed).*

## What it is

A longitudinal corpus of U.S. presidential *spoken* language — speeches, remarks,
news conferences, interviews — from Reagan to the present, built to study how
presidents' language (and what it suggests about cognition) changes over time.
Target ~20,000 transcripts. Runs locally in Python.

## What's been built (all in the repo)

- **Collectors** that politely scrape (rate-limited, cached, restartable) three
  sources: the **American Presidency Project** — the backbone, filtered to
  *spoken* categories only (speeches/remarks, not executive orders, proclamations,
  or other written documents) — plus the **Miller Center** and the **Trump/NARA
  archive**. (`scripts/collect_*.py`)
- **A pipeline**: normalize → dedupe → classify event type → compute metrics →
  report. (`scripts/run_pipeline.py`)
- **A deterministic NLP feature layer** using spaCy (POS, dependency-parse
  syntactic complexity, morphology), length-robust lexical diversity (MTLD/MATTR),
  and VADER sentiment — the reproducible backbone for longitudinal analysis.
  (`scripts/extract_features.py`)
- **A published-result validation**: we independently reproduced Berisha et al.
  (2015), which found Alzheimer's-associated language trends in Reagan's news
  conferences vs. Bush's (control). All six trend verdicts match, including the
  paper's exact sample sizes. See [`berisha_validation.md`](berisha_validation.md)
  (with figure). This is a *methods validation*, not a clinical claim.
- **Storage + GUIs**: everything loads into **PostgreSQL**
  (`scripts/load_to_postgres.py`); a **marimo** web dashboard and **pgweb** browse
  it live, querying Postgres directly (no data duplication).

## Where to look

- [`../README.md`](../README.md) and [`../HANDOFF.md`](../HANDOFF.md) — overview +
  current state
- [`tech_journal.md`](tech_journal.md) — methods log + results
- [`berisha_validation.md`](berisha_validation.md) — the validation write-up
- [`../scripts/`](../scripts/) — all the code

## Good questions to poke at

- Are the methods sound? What statistical pitfalls lurk in longitudinal speech
  analysis (length confounds, autocorrelation, multiple comparisons, speaker-vs-
  era effects)?
- Which additional linguistic / cognitive-linguistic features are worth adding?
- How robust is the president-only segmentation of news conferences?
- What would a credible control / null model look like across more presidents?

## Framing / caveats

This is exploratory research on the **public speech of public figures**. The
Reagan/Alzheimer's angle validates the methods against peer-reviewed work — it is
**not** used to diagnose anyone. The aim is rigorous, reproducible, longitudinal
linguistic analysis across administrations.

---

### Paste-ready prompt for an AI assistant

> I'm building a research project called the Presidential Cognition Corpus and I'd
> like your help understanding it and poking around. The code is public at
> https://github.com/munnecke/cognition (main project under
> `presidential_cognition_corpus/`). Please read the repo — start with `README.md`,
> `HANDOFF.md`, and `documents/project_brief.md` — then help me think about the
> soundness of the methods, features worth adding, statistical pitfalls in
> longitudinal speech analysis, and ethical framing. Ask me questions and push back.
> Note: the Reagan/Alzheimer's work validates the methods against a published study
> (Berisha et al. 2015); it is not used to diagnose anyone.
