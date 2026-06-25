# Plan — Semantic-coherence layer ("half-life of a thought")

*Status: DESIGN (not yet built). A deterministic, embedding-based layer measuring
topic maintenance / distractibility, parallel to the Berisha cognitive markers.
Anchored to the speech-coherence literature the way the cognitive layer is
anchored to Berisha et al. (2015).*

## Construct

How long does a single train of thought stay on topic before it drifts — and how
intact is the thread across an answer? This targets **tangentiality / loss of
topic maintenance**, a documented marker in cognitive decline and thought
disorder, on a new axis the current features (lexical diversity, syntax, idea
density, sentiment) do not touch.

## Literature anchors (ancestors)

- **Bedi et al. (2015, *npj Schizophrenia*)** — cosine similarity between
  consecutive phrases (LSA); minimum-coherence predicted psychosis onset. **Direct
  parent** — our measure is a decay-curve generalization of this.
- **Elvevåg, Foltz, Weinberger & Goldberg (2007, *Schizophr. Res.*)** — LSA-based
  semantic coherence distinguishes patients from controls. Method ancestor.
- **Mota et al. (2012/2014, *PLoS ONE*)** — speech-graph connectedness
  (words=nodes, sequence=edges) for psychosis/cognition. Alternative, complementary
  operationalization.
- **Graesser & McNamara — Coh-Metrix** — local vs global cohesion indices,
  connective density. Frames the local/global distinction below.
- **Andreasen (1986) — TLC scale** — defines *tangentiality* and *derailment* as
  clinical constructs; the targets these automated measures approximate.
- **Levelt (1983); Shriberg (1994)** — self-repair structure and the disfluency
  taxonomy. Ancestors for the self-interruption sub-measure (see caveat).

## Measures (refined — within-turn, not whole-document)

The naive whole-transcript decay conflates the speaker's topic maintenance with
the *interview's* turn structure (a president who holds the floor "gets credit";
one in rapid Q&A looks incoherent for format reasons). So we measure **within
continuous answers**, and treat turn dynamics as their own signals.

1. **Within-answer coherence half-life** — embed sentences; mean cosine similarity
   vs. sentence lag *k*, computed inside each president answer, aggregated. The
   half-life = lag where similarity falls halfway from its lag-1 value to the
   answer's baseline. *Short half-life = faster drift / distractibility.* The
   headline measure.
2. **Local vs global coherence** (Coh-Metrix framing) — local = adjacent-sentence
   similarity; global = each sentence vs the answer's centroid. Decline can show
   in either independently.
3. **Q→A relevance / tangentiality** — cosine(question, answer): did the answer
   engage the question? A deterministic cousin of the LLM "evasiveness" dimension.
4. **Turn-completion / trailing-off** *(low-confidence — see caveat)* — fraction of
   the president's turns that end mid-thought (APP `--`/`-- --` interruption marks,
   abandoned clauses). May reflect cognition OR transcription convention.

## Method notes

- **Embeddings:** bge-m3 (1024-d) via the local LM Studio endpoint (verified
  working); deterministic given the model → reproducible, model-versioned.
- **Anisotropy fix (required):** raw cosine on these embeddings is compressed
  (~0.47–0.55 baseline). Mean-center (remove the corpus mean, optionally the top
  principal component, à la "all-but-the-top") so the measure actually
  discriminates. The prototype showed the compression; this is the fix.
- **Shuffled-sentence null:** permute sentences, recompute → per-doc chance
  baseline; report coherence as distance above null (z).
- **Continuous half-life:** fit `sim(k) ≈ base + (sim0−base)·exp(−k/τ)`; report
  τ·ln2 (falls back to empirical crossing).

## The data-cleanliness caveat (honest scoping)

Presidential transcripts are **edited**: transcribers strip "um/uh," false starts,
and repetitions (we already see `filler_ratio ≈ 0`). So Shriberg/Levelt-style
**self-interruption counts mostly measure transcription convention, not the
speaker** — measure #4 is **exploratory and caveated**, never a headline. The
**coherence** measures (#1–3) are unaffected: Bedi/Elvevåg worked on transcribed
speech too, and embeddings handle cleaned text fine.

## Architecture

Deterministic → its own reproducible table **`speech_coherence`** (parallel to
`linguistic_features`, NOT `llm_extractions`), keyed by speech id, carrying the
embedding-model id + extractor version as provenance. Optionally store sentence
vectors in `pgvector` for reuse (semantic search, clustering). Embeddings are
deterministic, so this layer can't move the longitudinal trends the way a chat
model could.

## Validation & payoff

- **Face validity:** within-answer half-life should be longer in prepared formal
  addresses than in rapid exchanges; Q→A relevance lower where evasiveness is high.
- **Convergent check:** correlate with the LLM "evasiveness" affect dimension
  (should align on Q→A relevance) and with idea density.
- **The trajectory (the point):** per-president within-person regression of the
  half-life on years-into-administration — the **same Reagan test**, on a genuinely
  new axis. Does anyone's coherence half-life *shorten* over their term?

## Build steps (when approved)

1. `scripts/extract_coherence.py` — per answer-turn: sentence-split → bge-m3 →
   mean-center → local/global coherence, lag-decay half-life, Q→A relevance;
   write `speech_coherence`. Restartable, `--only-missing`, batched (embeddings are
   cheap and GPU-cached, so this is fast).
   *Reuses `segment_speaker` for turns; adds a question/answer pairer for #3.*
2. Add `speech_coherence` to `load_to_postgres.py` schema.
3. `scripts/coherence_trajectory.py` — the within-person half-life trajectory
   (mirrors `latent_trajectory_spontaneity.py`).
4. Validate on the impromptu set (spontaneity ≥ 0.5), then report.

## Open questions for review

- Order: coherence layer **before or after** the affect layer?
- Include the Q→A pairer now (enables both tangentiality here and evasiveness in
  the affect layer) or defer?
- Store sentence vectors in pgvector (reusable, more storage) or compute-and-discard?
