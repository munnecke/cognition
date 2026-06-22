# Technical Journal — Presidential Cognition Corpus

A running log of methods, experiments, and results. Newest entries at the top.

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
