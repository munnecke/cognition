# cognition

Research software for building and analyzing a longitudinal corpus of U.S.
presidential speech (Reagan → present), for linguistic / cognitive analysis.

The project lives in [`presidential_cognition_corpus/`](presidential_cognition_corpus/) —
see its [`README.md`](presidential_cognition_corpus/README.md) for the full spec
and [`HANDOFF.md`](presidential_cognition_corpus/HANDOFF.md) for current state.

## What's here

- **Collectors** — American Presidency Project, Miller Center, and Trump/NARA
  archive scrapers (polite, cached, restartable). APP collection is filtered to
  *spoken* material only (speeches & remarks, not written documents).
- **Pipeline** — normalize → dedupe → classify → metrics → report.
- **NLP feature layer** (`extract_features.py`) — deterministic spaCy features
  (POS/morphology, dependency-based syntactic complexity, length-robust lexical
  diversity, VADER sentiment) for the longitudinal analysis backbone.

## Data is not archived here

Only the software is version-controlled. All collected transcripts and generated
tables (`data_raw/`, `data_clean/`, logs) are kept local and excluded via
`.gitignore`; directory structure is preserved with `.gitkeep` placeholders.
