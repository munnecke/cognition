# Technical Journal — Presidential Cognition Corpus

A running log of methods, experiments, and results. Newest entries at the top.

---

## 2026-06-24 — Discourse-complexity LOWESS trajectory on the impromptu set

The multi-indicator composite ( complexity = mean(z(unique), z(idea_density),
-z(NS+fillers)) ), within-person, regressed on years-into-administration,
LOWESS-smoothed — same instrument as the 2026-06-22 news-conference trajectory,
but on the spontaneity ≥ 0.5 impromptu set. `scripts/latent_trajectory_spontaneity.py`
(imports `latent_trajectory` and swaps only the document selection). Figure:
`documents/discourse_complexity_trajectory_impromptu.png`.

| presidency | n | slope/yr | R | p |
|---|---|---|---|---|
| **Ronald Reagan** | 198 | **−0.034** | **−0.15** | **.034** |
| G.H.W. Bush | 196 | −0.044 | −0.13 | .069 |
| Clinton | 267 | +0.012 | +0.07 | .267 |
| G.W. Bush | 173 | +0.012 | +0.06 | .423 |
| **Barack Obama** | 175 | +0.054 | +0.28 | **.000** |
| Trump 1st | 181 | −0.015 | −0.03 | .740 |
| Trump 2nd | 181 | +0.104 | +0.08 | .318 |
| Biden | 31 | +0.012 | +0.02 | .902 |

**Reagan is the only significant DECLINE** (p=.034) — consistent with the
marker-level result and the original news-conference trajectory, now on a 4×
larger genre-diverse sample. It is **attenuated** vs the news-conference frame
(R=−0.15 here vs −0.45 then; slope −0.034 vs −0.088/yr) for two compounding
reasons: (a) genre heterogeneity in the impromptu set adds per-doc noise, and
(b) `idea_density` does not co-move with Reagan's decline (already noted
2026-06-22) so it dilutes the composite — the signal is carried by the two
validated Berisha markers, not idea density. **Obama shows a significant
*increase*** (p<.001) — a genuine rising-complexity trend, the opposite of
decline, not a false alarm. **Trump 2nd term is a clean null at real n=181** (was
~10) — the small-n problem is solved without manufacturing a signal.

Net across both analyses (markers + composite): on the LLM-selected impromptu
set, **Reagan uniquely shows the decline signature, and it survives a 4× sample
expansion across genres** — strengthening confidence it is real, not a
news-conference artifact.

---

## 2026-06-24 — Berisha markers on the LLM-selected impromptu set

With the corpus fully scored, re-ran the validated Berisha markers (unique words;
NS-nouns+fillers over chronological president-only answers, first 1,400 words,
Pearson vs index with >2 SD outlier drop) but selecting documents by the
spontaneity classifier instead of the title="news conference" filter.
`scripts/cohort_spontaneity.py` (reuses `replicate_berisha` + `segment_speaker`;
selection is the only change).

**Threshold matters — and revealed a genre effect.** At **≥0.7** every president
went null, *including Reagan*. Cause (verified): a formal news conference opens
with a prepared statement, so the classifier scores it **"mixed" (~0.54)** — only
**3 of Reagan's 138** news-conference docs clear 0.7. The ≥0.7 set is therefore a
*different genre* (brief pure-Q&A reporter exchanges, ~0.88), which excludes the
very documents Berisha studied. The decline signal is **genre-specific**: it lives
in sustained formal-news-conference Q&A, not short exchanges.

**At ≥0.5** (which includes the "mixed" news conferences) the result is clean and
strong:

| presidency | n | unique words | NS+fillers |
|---|---|---|---|
| **Ronald Reagan** | **198** | **−0.22 (.003)** | **+0.23 (.001)** |
| G.H.W. Bush | 196 | −0.00 ns | +0.05 ns |
| Clinton | 267 | −0.00 ns | +0.13 (.042) |
| G.W. Bush | 173 | +0.05 ns | −0.07 ns |
| Obama | 175 | +0.13 ns | −0.22 (.004, anti-decline) |
| Trump 1st | 181 | +0.12 ns | +0.10 ns |
| Trump 2nd | 181 | +0.08 ns | −0.04 ns |
| Biden | 31 | +0.28 ns | +0.26 ns |

**Reagan alone shows the full coherent decline signature** (both markers
significant, correct direction) — now on a **4× larger, genre-diverse sample**
(198 vs 46 news conferences) and with *stronger* significance (p=.003/.001 vs
.006/.004) despite an attenuated coefficient (−0.22 vs −0.41; expected from the
added genre heterogeneity). Single-marker hits (Clinton ns+fillers; Obama, which
is anti-decline) **fail the coherence test**, exactly as before. Crucially,
**Trump 2nd term now has real n (181, was ~10)** and is a clean null — the small-n
problem the classifier was built to solve is resolved, and it didn't manufacture
a signal.

Lesson for the method: "spontaneity ≥ θ" is not a single knob — θ selects a genre
mix. **≥0.5 is the right operationalization for the Berisha frame** (keeps the
news conferences); ≥0.7 measures a different, narrower register. Figures:
`documents/impromptu_{unique_words,ns_plus_fillers}_grid.png` (regenerated at 0.5).

---

## 2026-06-24 — Concurrency dedup + the Trump small-n payoff

Two `run_spontaneity_overnight.sh` instances ended up running at once (an earlier
runner survived a `pkill`; the date-priority chain started a second). Both score
with `--only-missing`, which is a check-then-write race: each reads "unscored,"
both write → **9,785 duplicate rows** in `llm_extractions`, concentrated in the
date range they overlapped (bush43 fully, clinton partially). Reagan/Bush41 (done
before the second started) and Trump (scored once by the priority pass) were clean.

Fix: killed both, deduped (kept lowest `id` per (speech_id, extraction_type,
prompt_version, model)), added a **UNIQUE index** on that tuple, and made the
scorer INSERT `... ON CONFLICT DO NOTHING`. Concurrent or restarted runs are now
idempotent at the storage layer, not just by the `--only-missing` query. Index
added to `load_to_postgres.py` so a rebuild keeps it. Relaunched a single runner.

**The payoff (Trump 2nd term, the original motivation):** the impromptu set grows
from **22** titled press conferences to **478** at spontaneity ≥ 0.5 and **165**
at ≥ 0.7 — i.e. 7.5×–22× more spontaneous material. The small-n problem (n≈10–22)
that made a 2nd-term trajectory un-runnable is resolved; there's now real power to
run the Berisha markers / discourse-complexity trajectory on both Trump terms.

---

## 2026-06-23 — Non-voice filter (`presidential_voice` flag)

Eyeballing the corpus surfaced material that is **not in the president's spoken
voice** — third-person White House comms output: disaster-declaration approvals
("President Donald J. Trump Approves California Disaster Declaration"), award
announcements, First/Second-Lady press releases, staff-only press briefings
(Press Secretary McEnany), Readouts, Joint Statements, Messages to Congress.
Source check: **590 of 591 are `whitehouse_archive`** — the Trump/NARA ingest the
HANDOFF flagged as never spoken-category-filtered (APP/Miller were filtered at
collection, so they're clean). These would skew any corpus-wide measure and waste
LLM time, and the classifier would (correctly) score them ~0.1 anyway.

`scripts/flag_nonvoice.py` adds a durable derived boolean `speeches.presidential_
voice` (default TRUE; FALSE for non-voice), idempotent + re-runnable. Matching is
**title-anchored and conservative** (user chose "precise, low false-positive"):
the title must START WITH a written-instrument/comms label, or be a third-person
"<Official> <Name> …" headline lacking any spoken marker — and we KEEP anything
explicitly spoken "by [the] President/Vice President". Final: **575 flagged**
(~1.2%), all `whitehouse_archive`, 0 APP.

Two bugs caught while tuning the predicate:
- A president-led "Press Briefing by President Biden, …" (the one APP match) is
  real voice — added the "by President/VP" carve-out so it (and 11 like it) stay,
  while 57 staff-only briefings remain excluded.
- **Postgres regex word boundary is `\y`, not `\b`** (`\b` = backspace, silently
  never matches). The negative guards used `\b`; switched to `\y`. No harm had
  occurred (the archive titles real remarks "Remarks by President …", which never
  hit the third-person arm), but the guard now actually works.

Wired into the scorer (`fetch_speeches` filters `presidential_voice`) and the
overnight runner's remaining-count. Voice-only corpus: **21,956** (was 22,212).
Re-run `flag_nonvoice.py` after any Postgres reload (it's a derived column).

---

## 2026-06-23 — Spontaneity classifier: model bake-off + corpus-wide run

The classifier (below) was built defaulting to gemma-4-26b, but gemma proved
**too slow at scale**, so we ran a four-model bake-off on a labelled 6-doc set
(2 scripted / 2 mixed / 2 spontaneous), scoring BOTH accuracy and throughput:

| model | accuracy | speed | verdict |
|---|---|---|---|
| llama-3.2-3b | can't discriminate (constant "mixed") | fast | rejected |
| gemma-4-26b-a4b | 5/6 | **~11 s/doc** | accurate but unscalable |
| gte-qwen2-7b | 0/6 (non-JSON, degenerates to looping CJK) | slow | embedding model, rejected |
| qwen2.5-**coder**-7b | 2/6 (over-calls everything spontaneous) | fast | wrong variant, rejected |
| **Qwen2.5-7B-Instruct (general, MLX 4-bit)** | **5/6** | **~3-4 s/doc** | **chosen** |

**Why gemma is slow — diagnosed from LM Studio logs.** gemma-4-26b-a4b is a
*reasoning* model with **sliding-window attention**; SWA defeats the prompt
cache ("cache reuse is not supported … forcing full prompt re-processing"), so
the full ~2.3k-token prompt is re-encoded **every doc** at ~224 tok/s ≈ 11 s.
Reloading the model didn't help (it's architectural, not state). gemma also
*degenerated into endless reasoning* on a ~5% tail of short ceremony docs,
emitting empty content (finish_reason='length') — not fixable by more tokens or
by disabling thinking (the knobs are ignored). A non-SWA instruct model (Qwen)
gets prefix-cache reuse and, as an **MLX build on Apple Silicon**, is markedly
faster on prompt processing — the bottleneck. GPU pegs at 100% (gemma did not).

**Prompt v2.** Sharpened the mixed-vs-spontaneous boundary: a brief one/two-line
framing before pure Q&A is *spontaneous* (0.8-1.0), not mixed — Qwen had been
collapsing all interactive docs to 0.5. This recovered the top band and took it
from 4/6 → 5/6. `PROMPT_VERSION='spontaneity-v2'`.

**Robustness fixes (this session):** `excerpt` capped at `--max-words` (now
**800** — benchmarked sweet spot: same accuracy as 1500, less prompt-eval; 500
broke); a **request timeout** + `max_retries` on the LLM client (a mid-run server
restart had hung the whole batch); retry-once-then-skip+log on empty output; and
a **key-tolerant score parser** — the 4-bit fine-tune occasionally misspells the
key (`spontivity`) while otherwise returning correct JSON, so we accept any
numeric `spont*` key rather than discard a good judgment.

**Corpus-wide overnight run.** `scripts/run_spontaneity_overnight.sh` — resilient,
resumable, batched (`--limit 500`, bounded memory), with a stuck-detector so it
won't hot-loop a dead endpoint. Scoring **all 22,208 canonical docs ≥200 words,
all 8 presidencies** at ~3-4 s/doc (~20 h wall → spans a couple of nights;
`--only-missing` resumes). Early distribution looks right (scripted ≈0.06,
mixed ≈0.51, spontaneous ≈0.85). Model of record: `josiefied-qwen2.5-7b-
instruct-abliterated-v2-4-bit` (a general-instruct build; the stock
`Qwen2.5-7B-Instruct` MLX 4-bit is the reproducible equivalent).

**Next:** once scored, pick an impromptu threshold from the score distribution,
confirm the impromptu set grows (Trump 2nd term was 22 press-confs → expect many),
and re-run the Berisha/trajectory analyses on the LLM-selected set.

---

## 2026-06-22 — LLM spontaneity classifier (the smarter impromptu selector)

Built `scripts/llm_spontaneity.py` to address the Trump small-n problem: the
"impromptu" set used by the Berisha-style longitudinal markers was defined by a
brittle *title* filter (title ≈ "news conference"), which gives only **22**
press conferences for Trump's 2nd term — too few to regress. The classifier
reads the actual text and scores each transcript's spontaneity on 0..1, so the
impromptu set becomes `spontaneity ≥ threshold` — pulling in exchanges-with-
reporters, Q&A, interviews, town halls already in the corpus.

**Storage / provenance.** One row per (speech, model, prompt_version) in
`llm_extractions`: `extraction_type='spontaneity'`, `extracted_pattern`=label
(scripted/mixed/spontaneous), `confidence_score`=score, `raw`=full JSON
(reason + evidence quote + excerpt provenance). Kept separate from the
deterministic `classify_event_type.prepared_or_impromptu` (structural, in
`speeches`) so a model/prompt change can't move the longitudinal trend lines.
Idempotent via `--only-missing`; restartable; `--sample N` prints without writing.

**Model choice — benchmarked, and it overturned the plan.** The handoff planned
to use the *fast* `llama-3.2-3b`. On a labelled sample of **full transcripts**
the 3B model **cannot discriminate**: with a loose prompt it defaulted to
"scripted", and with a sharpened prompt it collapsed to a constant "mixed,
interactive" — labelling even a scripted Inaugural Address as a Q&A it
hallucinated. `gemma-4-26b` was correct on every case (Inaugural/Address-to-
Nation → scripted; news conference → mixed+interactive with accurate reasoning).
A wrong spontaneity label poisons the set we then select from, so **accuracy wins
over speed here**: default is now gemma (~4 s/doc; llama left as a `--model`
override). The earlier "verified llama tags spontaneity" note held only for short,
clean inputs, not real transcripts.

**A gemma quirk, characterized.** gemma deterministically returns an *empty*
completion on a ~5% tail of inputs (measured 2/40 on a random candidate sample) —
specifically short ceremony/transition "Exchange With Reporters" remarks. It is
not load (3 sequential retries empty), not temperature (empty at 0.0–0.8), not
content-safety (the text is benign signing-ceremony remarks), and not data
corruption (the stored text is clean — the "s-less" rendering I first saw was a
*psql display* glitch, `full_text` is intact). An assistant-prefill (`{"reason":`)
breaks the empty but then degenerates ("by-by-by-by"). Handling: retry once with a
temperature bump (catches genuine transients), then **skip+log** the persistent
failures — they are tiny docs well below the 1,400-word analysis bar, so the loss
is benign. `llm.json_chat` gained an optional `temperature` arg for the retry.

**Excerpt sampling.** Head (60%) + middle (40%) slice capped at `--max-words`
(default 1500) so long Trump transcripts can't blow up latency/memory (the
HANDOFF OOM caution) while still surfacing Q&A that starts after a long opening.

**Run in progress.** Scoring Trump's **2nd term** candidate-spontaneous genres
(`--presidents trump --since 2021-01-20`, 565 docs). Added `--since/--until`
date filters (natural for this date-keyed longitudinal corpus). Next: pick a
threshold from the score distribution, confirm the 2nd-term impromptu set grows
from 22 → many, then scale to 1st term / the full cohort and re-run the
trajectory analyses on the LLM-selected set.

---

## 2026-06-22 — Latent integrity trajectory, all 8 presidencies

Re-ran the multi-indicator integrity composite ( z(unique) + z(idea_density) −
z(NS+fillers), within-person over time, news-conference frame) across the full
cohort. `scripts/latent_trajectory.py` (now all 8, Trump S/V split, full names).

**Only Reagan declines significantly: R=−0.44, p=0.003.** Everything else n.s.

The composite **resolves the single-marker false alarms**:
- **Biden** screamed on NS+fillers alone (R=+0.85, p<.001), but his composite is
  **n.s. (−0.32, p=0.29)** because his vocabulary is simultaneously *rising* (+0.47)
  — the markers disagree, so requiring coherence correctly declines to flag it.
- **Trump (2nd)** likewise n.s. (n=10).

This is the payoff of the multi-indicator construct vs. single charts: it isolates
the one coherent case (Reagan) and rejects noisy single markers. Reading caveat:
the Trump lines sit *low* (level — driven by register-confounded lexical diversity),
which is not the same as a downward *slope*. Caveats unchanged: small n for
Trump-2nd/Biden; news-conferences only; exploratory, not diagnostic.

*Refinement (same day): renamed the composite **discourse complexity index** (after
Berisha's "Tracking Discourse Complexity," less loaded than "integrity"); x-axis is
now **years into the administration** so the slope is a real per-year rate, comparable
across 4-/8-year terms; lines labelled directly for print. Conclusion unchanged —
only Reagan significant (−0.088/yr, R=−0.45, p=0.003). Final styling: **LOWESS-smoothed
curves** (gentle frac, near-linear at small n so they don't overfit), legend moved off
the plot, and Trump anchored to his **2017 inauguration** so both terms share one
timeline (1st at yrs 0–4, 2nd at 8–10) with the out-of-office gap visible. Figure:
`documents/discourse_complexity_trajectory.png`.*

---

## 2026-06-22 — Berisha charts extended to all 8 presidencies

Reproduced Berisha et al. Figure 1 (unique words; NS-nouns+fillers over chronological
news conferences) for *every* presidency, full-name labels (Trump split S/V).
`scripts/cohort_figures.py`; figures in `documents/cohort_*`.

| presidency | n | unique words | NS+fillers |
|---|---|---|---|
| Ronald Reagan | 46 | **−0.41 (.006)** | **+0.42 (.004)** |
| George H.W. Bush | 101 | −0.14 ns | +0.02 ns |
| Bill Clinton | 82 | +0.03 ns | +0.18 ns |
| George W. Bush | 52 | +0.16 ns | −0.11 ns |
| Barack Obama | 62 | +0.13 ns | −0.28 (.031) |
| Trump (1st) | 37 | +0.06 ns | +0.04 ns |
| Trump (2nd) | 10 | −0.40 ns | −0.33 ns |
| Joseph R. Biden | 14 | +0.47 ns | **+0.85 (<.001)** |

**Only Reagan shows the full coherent signature** (both markers significant, decline
direction) — across the whole cohort, his alone.

**Biden** has the one statistically loud single result (NS+fillers R=+0.85, p<.001,
survives Bonferroni) — **but it fails coherence**: his unique words *rise* (+0.47), the
opposite of decline, so the two markers disagree (same failure mode as Trump S→V), on
n=14. A noisy single marker, **not the decline signature, not a finding**. Obama's
NS+fillers *decrease* (anti-decline). Others null.

**Lesson:** a single chart can mislead (Biden in isolation looks alarming); coherence
across markers — the latent-integrity composite — is the honest instrument. Caveats:
small n for Trump-2nd (10) / Biden (14); 16 comparisons; news-conferences only;
exploratory, not diagnostic.

---

## 2026-06-22 — Latent integrity trajectory (the Berisha upgrade)

Built a multi-indicator **cognitive-linguistic integrity** composite
( z(unique_words) + z(idea_density) − z(NS-nouns+fillers) ) and regressed it
*within each president over time*, in the validated news-conference frame.
`scripts/latent_trajectory.py`.

### Result (coded-first; n=5 presidents)
| | integrity slope | verdict |
|---|---|---|
| **President K (Reagan)** | **R=−0.480, p=0.001** | **significant decline** |
| President M (G.H.W. Bush) | −0.162, p=0.11 | null |
| President N (Clinton) | −0.146, p=0.20 | null |
| President H (G.W. Bush) | +0.210, p=0.14 | null |
| President P (Obama) | +0.132, p=0.31 | null |

Reagan's integrity composite declines significantly and **uniquely** — and *more
cleanly than any single marker* (composite p=0.001 vs. unique-words p=0.006).
Combining indicators sharpens the signal, exactly as the multi-indicator logic
predicts. Survives Bonferroni (0.05/5 = 0.01).

### Honest caveats
- **`idea_density` did NOT contribute** to Reagan's decline (R=+0.27, n.s. — slightly
  *opposed* it). The composite's power comes from the two validated Berisha markers
  (unique-words ↓, NS+fillers ↑). Not every indicator co-moves; the composite is
  robust because 2 of 3 align strongly.
- **Circularity:** the composite reuses the Berisha markers, so this is a robustness /
  construct generalization, **not independent new evidence** — it shows the signal
  holds as a latent construct, not that we've found a new one.
- Exploratory, not diagnostic; news-conferences only; 5 presidents.

### Next
The full pass adds `idea_density` corpus-wide, syntactic-complexity indicators,
and Trump (S/V) + Biden (L) — enabling a richer, less circular composite and the
complete cohort.

---

## 2026-06-22 — Exploratory latent-factor analysis (preliminary)

*Reframed "deep structure" → modern latent-variable modeling: are there underlying
factors organizing the surface markers? Factor analysis (varimax) on 18 markers,
18,482 speeches, 5 presidents. `scripts/latent_factors.py`.*

### Findings
~60% of variance in 4 factors (first two dominate, 27% + 18%). Interpretable axes:
- **F1 Syntactic complexity** (clauses/sentence, subordination, tree depth, dep. distance)
- **F2 Verbal ↔ nominal** (verb-heavy vs noun/adjective-heavy)
- **F3 Lexical diversity** (MTLD, MATTR)
- **F4 Noun density / concreteness** (noun-heavy, low function words/hedges)

Per-president factor scores (coded) **recover the earlier descriptive differences** —
a consistency check that the factors are real: K (Reagan) top diversity; H (G.W. Bush)
simplest syntax + most nominal; N/P (Clinton/Obama) most complex.

The **within-person** factor structure mirrors the pooled one → the loud axes are
style + genre, operating both between and within presidents (a formal address vs a
Q&A varies the same way presidents differ from each other).

### What it does / doesn't answer
It confirms there *are* interpretable underlying factors (dominated by syntactic
complexity + lexical diversity). It does **not** yet test "a factor driving *change*
over time" (the dementia hypothesis) — this is the *static* factor structure, not its
trajectory. **Next step:** project each president's speeches onto the factors and
regress factor scores against time *within-person* (a latent-construct trajectory —
the Berisha time-trend logic applied to a multi-indicator construct). `idea_density`
(arriving in the full pass) should strengthen a "cognitive-linguistic integrity"
factor (diversity + idea density − non-specific nouns).

---

## 2026-06-22 — First cross-president analyses (preliminary, 5 presidents)

*Preliminary — run on the 5 complete presidencies (Reagan→Obama); Trump (S/V) and
Biden (L) still collecting, and `idea_density` not yet in the corpus. All
coded-first via the neutral identifiers.*

### Cohort longitudinal trends (`scripts/cohort_figures.py`)
Extended the validated Berisha method (unique words / NS-nouns+fillers over
chronological news-conference answers) across the cohort. **Only President K
(Reagan) shows the full decline signature** — unique words ↓ (R=−0.41) *and*
NS+fillers ↑ (R=+0.42), both significant; every control is null. The method
*discriminates* (one of five pops) rather than flagging everyone — the reassuring
outcome. Caveat: exploratory, not diagnostic; small multiple-comparison budget.

### Cross-president style/affect comparison (`scripts/compare_features.py`)
Coded-first means across all spoken genres. **Me/Us focus is the big
differentiator**: President M most "I"-leaning (1.13), President P most "we"-leaning
(0.59). President K highest lexical diversity; President H lowest + simplest syntax.
The patterns match recognizable styles (P = collective rhetoric, H = plain-spoken) —
a validity check that the features capture something real. Caveats: genre-mixed
(not controlled), levels not trends.

(Reveal: K=Reagan, M=G.H.W. Bush, N=Clinton, H=G.W. Bush, P=Obama.)

---

## 2026-06-22 — Parallelized feature extraction (measured 3.2×)

### Decision
Add `--n-process` to `extract_features.py` (spaCy `nlp.pipe(n_process=N)`) to use
the idle cores. Single-process extraction was pinning exactly **1 of 12 cores** on
an M4 Pro (8 performance + 4 efficiency) — the machine was mostly loafing.

### Benchmark (1,000 docs, en_core_web_sm, same inputs)
| | wall time | throughput |
|---|---|---|
| 1 core | 121.3 s | 8.2 docs/sec |
| 8 workers | 38.2 s | 26.2 docs/sec |
| **speedup** | | **3.2×** |

### Why 3.2×, not 8×
`nlp.pipe(n_process)` parallelizes only the **spaCy parse**; our `compute_features`
+ VADER run **serially in the main process** (Amdahl), plus multiprocessing /
per-worker model-load overhead. Near-linear scaling would require sharding the
*whole* per-doc pipeline across processes — deferred (3.2× is a solid win for a
one-line change).

### Context
Collection is **network / rate-limit bound**, not compute — more workers don't
help it (and would be impolite to one server). This lever is for the local-compute
stages: feature extraction now; embeddings and the LLM affect layer later (those
will also light up the currently-idle GPU via Apple MPS / LM Studio).

---

## 2026-06-22 — Design: keep the corpus open to pre/post-presidential language

### Intent
Keep the architecture able to later incorporate language from *outside* the
official presidential term — pre-presidential (campaign, earlier-career interviews,
social media in the run-up) and post-/between-presidency — without reworking the
core. **Not building it now**; recording the design seams so it stays open.

### Why it fits naturally
The right unit for cognitive-trajectory work is the **person across time**, with the
presidency as one labeled *phase*; a longer time series is strictly better for
detecting longitudinal change. Affordances already present:
- Documents keyed by person + **date** (the longitudinal axis is phase-agnostic).
- `campaign_or_official` and `source` metadata fields already exist.
- Trump is already collected from the **2015 campaign** (model handles pre-office
  material), and his terms split by date — a special case of phase labeling.
- Drop-folder ingest already accepts non-archive sources (interviews, rally,
  YouTube) — the natural path for social media / podcast transcripts.

### Extension seams (to implement when real pre/post data arrives — not now)
- **Separate "term boundaries" from "collection window."** Today `collect_from/to`
  serve both; to harvest pre/post material we'd widen collection while keeping the
  official term for labeling → add explicit `term_start`/`term_end`.
- **Generalize `life_phase(person, date)`** = pre / campaign / term-N / between /
  post. The current Trump date-split is its first instance.
- **Social media is a distinct register** (short, high-volume, different norms) —
  its own `source`, carrying the existing `quality_score`/`machine_generated` flags,
  analyzed with register-aware care.

### Decision
Document the seams; **don't pre-abstract** (premature abstraction is its own
anti-pattern). Current work (neutral IDs, affect features, Postgres schema keyed by
person+date+source) is already phase-agnostic and won't preclude the extension; the
phase model gets built when the first out-of-term data is actually added.

---

## 2026-06-22 — Neutral president identifiers (de-biasing device)

### Decision
Comparative and affect outputs will default to **neutral symbolic labels**
("President K", "President M", …) rather than names, revealing identity only after
the pattern has been examined ("coded first, revealed second").

### Reasoning
Public figures carry strong political/emotional associations; naming them invites
readers (and us) to import priors into the interpretation of linguistic results.
Following an idea associated with **Bertrand Russell** (reformulating charged
questions with abstract placeholders to expose structure before ideology), neutral
identifiers act like a **blinded analysis** for exploratory/comparative work —
most valuable for affect variables (anger, Me/Us focus, sentiment) where priming
is worst.

It is explicitly **not anonymization**: dates and specific analyses make identities
obvious, and we deliberately name names where the science requires it (the Berisha
replication; Reagan's diagnosis). It's a presentation-order device, not concealment.

### Choices made (and why)
- **Letters** avoid culturally loaded ones — A/F (grades), X (unknown), Z
  (sleepy), Q (contemporary political) — and we additionally dropped **T** (a Trump
  monogram) and **R** (Reagan / "Republican" ballot letter) after recognizing they
  carry exactly the associations we're trying to neutralize. Also avoided W/G (the
  Bushes). Final set: H, K, L, M, N, P, S, V.
- **Assignment** is arbitrary and fixed, chosen so no letter matches its
  president's initial (so the letter itself doesn't leak the name).
- **Trump's two non-consecutive terms are split** into separate presidencies
  (President S = 1st, V = 2nd), because the four-year gap may itself reveal a
  longitudinal change in linguistic capability — a within-person comparison worth
  preserving. Implemented as a date split (2021-01-20) at the presentation layer;
  collection still uses one `trump` key, so nothing in the scraper changed.

Implemented in `scripts/common.py` (`neutral_code`, `neutral_label`,
`CODE_TO_PRESIDENT`); rationale + table in `documents/neutral_identifiers.md`.

---

## 2026-06-22 — Open science: license, citation, and idea lineage

### What and why
To make "completely open, validate or extend as you see fit" real and citable:
- **MIT license** on the software (`LICENSE`). The collected transcripts are *not*
  redistributed — the underlying official remarks are largely US public domain
  (17 USC §105), but source transcriptions/databases (APP, Miller) carry their own
  terms, so we ship the *method* and keep data local (`README` documents this).
- **`CITATION.cff`** for a permanent "Cite this repository" entry (affiliation:
  Cosmos Research Center); a Zenodo DOI from a tagged release is the planned
  permanent identifier.
- **`LINEAGE.md`** — an Engelbart-inspired *evolutionary attribution* structure:
  explicit **ancestors** (Berisha 2015, the Nun Study, Le et al., Bird et al.,
  Gottschalk, Pennebaker, Engelbart) and open **descendants**, extendable by PR.
  The project is self-exemplifying — it demonstrates the attribution method on its
  own development. Intended eventually as a Cosmos Research Center case study.

The validation was also packaged for sharing: `documents/berisha_validation.md`
(+ `.png` figure via `scripts/validation_figure.py`, + PDF), and a paste-ready
overview in `documents/project_brief.md`.

---

## 2026-06-22 — Storage + web GUIs (Postgres, no duplication)

### What and why
The flat-file corpus is the durable source of truth, but relational storage suits
the 1:1 features / 1:many LLM-extractions / cross-president longitudinal queries.
- **`scripts/load_to_postgres.py`** — idempotent load into Postgres
  (`presidents`, `speeches` + full_text + tsvector FTS, `linguistic_features`,
  `llm_extractions`). Keyed on the deterministic speech id; re-runnable as the
  corpus grows. Files stay the source of truth; the scraper isn't coupled to the DB.
- **GUIs query Postgres directly** (`scripts/serve_gui.sh`): a **marimo** dashboard
  (`scripts/dashboard.py`) that reuses our own code (it calls `replicate_berisha`
  live), and **pgweb** for raw browsing. Chosen over Metabase/Datasette because the
  user flagged the duplicate-database / sync problem of a SQLite mirror — marimo is
  a `.py` file in the repo querying Postgres live, so there's no second store to
  manage. The earlier Datasette/SQLite-mirror path was retired.

---

## 2026-06-22 — Method validation: replicating Berisha et al. (2015)

### Goal
Before trusting our own longitudinal measures, validate the full pipeline
(collection → segmentation → feature extraction → statistics) against a
published, peer-reviewed result on the *same* data source.

**Reference:** Berisha, Wang, LaCross & Liss (2015), "Tracking Discourse
Complexity Preceding Alzheimer's Disease Diagnosis: A Case Study Comparing the
Press Conferences of Presidents Ronald Reagan and George Herbert Walker Bush,"
*J. Alzheimers Dis.* 45(3):959–963. doi:10.3233/JAD-142763
(`documents/nihms-1062581.pdf`).

The paper analyzes Reagan's news conferences (diagnosed with Alzheimer's in 1994)
against George H.W. Bush's (no known diagnosis), and finds that **Reagan's
spontaneous speech shows a significant decline in unique words and a significant
rise in non-specific nouns + fillers over his presidency**, while Bush shows no
such trends — detectable years before Reagan's clinical diagnosis.

### Method (as reproduced)
1. **Source.** APP *news conferences*, chronologically ordered. We independently
   collected **exactly 46** Reagan news conferences — matching the paper's "46 of
   46" — a first sign our collection matches their source.
2. **Segmentation.** Keep only the president's *spontaneous answers*: drop the
   prepared opening statement, all reporters' questions/other speakers, APP's
   editorial topic headers, and bracketed stage directions (`[Laughter]`).
   (`scripts/segment_speaker.py`.)
3. **Length control.** Lexical stats are length-dependent, so restrict to the
   first 1,400 words and keep only transcripts that reach 1,400 (the paper's
   threshold; the shortest Reagan record).
4. **Features.** Per transcript: unique words (Lancaster-stemmed), non-specific
   nouns (tokens containing "thing"), fillers `{well, so, basically, actually,
   literally, um, ah}`, and low-imageability verbs.
5. **Statistics.** Per-feature >2 SD outlier removal, then Pearson correlation of
   each feature against chronological transcript index. (`scripts/replicate_berisha.py`.)

### Results

**Reagan (1981-01-29 .. 1988-12-08, n=46) — 3/3 verdicts match:**

| feature           | ours R | ours p | Berisha R | Berisha p | verdict | match |
|-------------------|-------:|-------:|----------:|----------:|---------|:-----:|
| unique_words      | −0.406 | 0.0062 |    −0.446 |     0.002 | sig-neg |  ✓    |
| ns_plus_fillers   | +0.423 | 0.0038 |    +0.358 |     0.017 | sig-pos |  ✓    |
| li_verbs          | +0.055 | 0.7312 |    +0.032 |     0.835 | null    |  ✓    |

**Bush 41 (control, COMPLETE term 1989-1992, n=101) — 3/3 verdicts match (all null):**

| feature           | ours R | ours p | Berisha R | Berisha p | verdict | match |
|-------------------|-------:|-------:|----------:|----------:|---------|:-----:|
| unique_words      | −0.138 | 0.179  |    −0.098 |     0.343 | null    |  ✓    |
| ns_plus_fillers   | +0.017 | 0.865  |    +0.053 |     0.608 | null    |  ✓    |
| li_verbs          | +0.042 | 0.682  |    −0.099 |     0.333 | null    |  ✓    |

*(Updated 2026-06-22 once Bush's full term finished collecting — exactly 101 of
137 conferences clear the 1,400-word threshold, matching the paper. The marginal
unique-word artifact seen on the overnight-truncated data, p=0.046, cleared to
p=0.179 on the complete term. Final tally: 6/6 verdicts match.)*

### Interpretation
- **Reagan replicates cleanly.** Both headline AD-signal trends reproduce as
  significant in the same direction, and the LI-verb null reproduces. The small
  coefficient differences (−0.406 vs −0.446) are expected from independent
  reimplementation (segmentation heuristics, tokenizer, outlier edges); the
  *scientific conclusions are identical.*
- **Bush control: clean (after full collection).** All three null results
  reproduce. An earlier run on the overnight-truncated Bush set (ended 1991-11-08,
  missing 1992) showed a spurious marginal unique-word trend (p=0.046); re-running
  on his **complete** term cleared it to p=0.179 (null), matching the paper — a
  good reminder that longitudinal trends are sensitive to full-span coverage.

**Verdict: pipeline validated against published work.** Notes on `li_verbs`: the
14-verb low-imageability set is an approximate light-verb list pending exact
confirmation from Bird et al. (2000); it showed no significant trend in the
original, so it does not affect the validation.

### Code used to generate this

Full scripts: `scripts/segment_speaker.py`, `scripts/replicate_berisha.py`. The
essential generating functions:

**President-only segmentation** (`segment_speaker.president_answers`):

```python
_PRES = re.compile(r"^\s*(?:The President|THE PRESIDENT)\.\s*")
_QUESTION = re.compile(r"^\s*(?:Q\b[.:]?|QUESTION[.:]|REPORTER[.:]|MODERATOR[.:])", re.I)
_BRACKET = re.compile(r"\[[^\]]*\]")

def president_answers(body: str) -> str:
    paragraphs = re.split(r"\n\s*\n", body)
    state, seen_question, kept = None, False, []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if _QUESTION.match(p):                 # a reporter question
            state, seen_question = "other", True
            continue
        m = _PRES.match(p)
        if m:                                  # a president turn
            state = "pres"
            if seen_question:                  # skip the opening prepared statement
                kept.append(p[m.end():])
            continue
        if _is_topic_header(p):                # APP editorial topic label
            continue
        if state == "pres" and seen_question:  # continuation of an answer
            kept.append(p)
    text = _BRACKET.sub(" ", " ".join(kept))   # drop [Laughter] etc.
    return re.sub(r"\s+", " ", text).strip()
```

**Berisha feature extraction** (`replicate_berisha.berisha_features`):

```python
_WORD = re.compile(r"[A-Za-z']+")
_STEM = LancasterStemmer()
FILLERS = {"well", "so", "basically", "actually", "literally", "um", "ah"}

def berisha_features(pres_text: str, max_words: int = 1400) -> dict | None:
    words = _WORD.findall(pres_text.lower())
    if len(words) < max_words:
        return None                            # below the 1,400-word threshold
    words = words[:max_words]
    stems = [_STEM.stem(w) for w in words]
    ns_nouns = sum(1 for w in words if "thing" in w)
    fillers = sum(1 for w in words if w in FILLERS)
    return {
        "unique_words": len(set(stems)),
        "ns_nouns": ns_nouns, "fillers": fillers,
        "ns_plus_fillers": ns_nouns + fillers,
        "li_verbs": sum(1 for w in words if w in LI_VERBS),
    }
```

**Chronological regression with outlier removal** (`replicate_berisha.regress`):

```python
def regress(rows, feature):
    idx = np.arange(len(rows))
    vals = np.array([r[feature] for r in rows], dtype=float)
    keep = np.abs(vals - vals.mean()) <= 2 * vals.std()   # >2 SD outlier drop
    r, p = stats.pearsonr(idx[keep], vals[keep])
    return {"R": round(float(r), 3), "p": round(float(p), 4), "n": int(keep.sum())}
```

Reproduce with:

```bash
python scripts/replicate_berisha.py --president reagan bush41
```

---

## 2026-06-21 — Corpus build

- Collectors verified live against all three sources (American Presidency Project,
  Miller Center, Trump/NARA archive); fixed president-attribution bugs (explicit
  speaker block / single-administration defaults) and non-speech-page leakage.
- APP collection filtered to **spoken material only** (speeches & remarks) via the
  `category2[]` advanced-search filter — ~112k all-types docs → ~22.5k spoken,
  ~66h → ~13h. See `HANDOFF.md`.
- Added deterministic NLP feature layer (`scripts/extract_features.py`): spaCy
  POS/dependency/morphology, length-robust lexical diversity (MTLD/MATTR), VADER
  sentiment — written to a separate `linguistic_features` table keyed by speech id.
