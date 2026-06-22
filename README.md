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

## License

The **software** in this repository is released under the [MIT License](LICENSE).
See [`CITATION.cff`](CITATION.cff) to cite it and [`LINEAGE.md`](LINEAGE.md) for
the idea's ancestors/descendants.

## Source data and its licensing

This repository contains **code only — no collected transcripts.** The collectors
fetch text from third-party archives *at run time*; that text is governed by each
source's terms, **not** by this repo's MIT license:

- The **underlying** official U.S. presidential remarks are generally works of the
  U.S. Government and thus public domain (17 U.S.C. § 105).
- However, the specific **transcriptions, editorial annotations, and curated
  databases** (American Presidency Project, Miller Center) carry their own terms of
  use. Wholesale redistribution of a scraped corpus can conflict with those terms
  (and with database/compilation rights) even where the underlying words are public
  domain.
- Some optional sources (Rev.com, YouTube captions, factba.se) are explicitly
  copyrighted/restricted; they are handled only via local manual ingest and are
  **never** redistributed.

Accordingly we distribute the **method** (collectors + pipeline) and keep the
collected text local (`data_raw/`, `data_clean/`, logs are git-ignored; directory
structure is preserved with `.gitkeep`). Anyone reproducing the corpus runs the
collectors themselves, subject to each source's terms and `robots.txt`. *This is
not legal advice — verify each source's current terms for your use.*
