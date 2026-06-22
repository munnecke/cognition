# Backlog — deferred ideas

Captured so they aren't lost. Nothing here is urgent; pull from it when relevant.

## Performance / infrastructure
- [ ] **GPU demo** — exercise the idle Apple-Silicon GPU with an embeddings batch
  (sentence-transformers on MPS) or `en_core_web_trf`, visible in Activity Monitor's
  GPU History. *(Deferred 2026-06-22.)*
- [ ] **Near-linear feature-extraction parallelism** — `--n-process` currently
  parallelizes only the spaCy parse (measured 3.2×); the serial tail is
  `compute_features` + VADER in the main process. Shard the *whole* per-doc pipeline
  across processes for closer to ~8×. *Only if feature passes become a bottleneck —
  3.2× is fine for now.* *(Deferred 2026-06-22.)*

## Analysis / data (already designed for; see tech_journal.md)
- [ ] **Pre/post/between-presidential language** — campaign, earlier interviews,
  social media, post-office. Keep building phase-agnostic; implement the
  `term_start/end` vs collection-window split + `life_phase()` when real out-of-term
  data is added.
- [ ] **Embeddings / semantic layer** (pgvector) and the **LLM affect layer**
  (anger/emotion extraction) — both also exercise the GPU.
