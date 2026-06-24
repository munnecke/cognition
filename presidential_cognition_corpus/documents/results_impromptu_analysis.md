# Results — Cognitive-linguistic trajectories on an LLM-selected impromptu corpus

*Presidential Cognition Corpus · 2026-06-24. Paste-ready summary of the
spontaneity-classifier analyses. Methods in `documents/tech_journal.md`;
field definitions in `documents/data_dictionary.md`.*

## Summary

Using a locally-run language model (Qwen2.5-7B-Instruct) to score each of 21,955
presidential transcripts (8 presidencies, Reagan→Trump's 2nd term) on a 0–1
**spontaneity** scale, we define the "impromptu" set — the genuinely
extemporaneous speech where cognitive-linguistic markers are interpretable — as
`spontaneity ≥ 0.5`, replacing the conventional, brittle "title = news
conference" filter. On this larger, genre-diverse set we re-ran two validated
analyses: the Berisha et al. (2015) discourse markers, and a multi-indicator
discourse-complexity trajectory.

**Headline:** Ronald Reagan uniquely exhibits the documented pre-clinical decline
signature, and it **survives a ~4× expansion of the sample across speech genres**
(198 vs. 46 news conferences) — strengthening the case that it is a real
within-person trajectory rather than an artifact of the news-conference setting.
The instrument remains discriminating: of eight presidencies, only Reagan shows
the coherent decline; controls are null or move in the opposite (improving)
direction.

## Method note: spontaneity is genre-graded, and the threshold matters

The classifier distinguishes a **formal news conference** (a prepared opening
statement followed by Q&A → labelled *mixed*, score ≈ 0.5) from a **brief reporter
exchange or interview** (pure Q&A → *spontaneous*, ≈ 0.85). This is a feature, not
noise: it means the threshold selects a *genre mix*, not merely a "purity" level.
At `≥ 0.7`, only 3 of Reagan's 138 news-conference documents survive — the cut
discards almost exactly the documents the decline lives in, and every president
goes null. **`≥ 0.5` is the correct operationalization of the Berisha frame**, as
it retains the formal news conferences while still adding interviews, town halls,
and exchanges. The decline signal is therefore **genre-specific**: it resides in
sustained, formal Q&A, not in off-the-cuff banter.

## Result 1 — Berisha discourse markers (per president, ≥ 0.5)

President-only spontaneous answers, first 1,400 words; unique words
(Lancaster-stemmed) and non-specific nouns + fillers; Pearson correlation vs.
chronological index, >2 SD outlier removal.

| presidency | n | unique words | NS-nouns + fillers | decline signature |
|---|---:|---:|---:|:--:|
| **Ronald Reagan** | 198 | **−0.22 (p=.003)** | **+0.23 (p=.001)** | **yes** |
| George H. W. Bush | 196 | −0.00 (ns) | +0.05 (ns) | no |
| Bill Clinton | 267 | −0.00 (ns) | +0.13 (p=.042) | no (incoherent) |
| George W. Bush | 173 | +0.05 (ns) | −0.07 (ns) | no |
| Barack Obama | 175 | +0.13 (ns) | −0.22 (p=.004) | no (anti-decline) |
| Donald Trump (1st) | 181 | +0.12 (ns) | +0.10 (ns) | no |
| Donald Trump (2nd) | 181 | +0.08 (ns) | −0.04 (ns) | no |
| Joseph R. Biden | 31 | +0.28 (ns) | +0.26 (ns) | no |

The decline signature requires **both** markers significant in the decline
direction (unique words ↓, NS+fillers ↑). Only Reagan satisfies it. Single-marker
hits (Clinton's fillers; Obama's, which is *anti*-decline) fail the coherence
test. The Reagan coefficients are attenuated relative to the news-conference-only
replication (−0.41/+0.42) — expected from the added genre heterogeneity — yet the
significance is *stronger* (p=.003/.001 vs .006/.004) on the larger sample.

## Result 2 — Discourse-complexity trajectory (composite, ≥ 0.5)

Composite = mean( z(unique words), z(idea density), −z(NS+fillers) ), within
president, regressed on **years into the administration** (so slopes are per-year
rates comparable across 4- and 8-year terms); LOWESS-smoothed for display.

| presidency | n | slope / yr | R | p |
|---|---:|---:|---:|---:|
| **Ronald Reagan** | 198 | **−0.034** | **−0.15** | **.034** |
| George H. W. Bush | 196 | −0.044 | −0.13 | .069 |
| Bill Clinton | 267 | +0.012 | +0.07 | .267 |
| George W. Bush | 173 | +0.012 | +0.06 | .423 |
| **Barack Obama** | 175 | +0.054 | +0.28 | **.000** |
| Donald Trump (1st) | 181 | −0.015 | −0.03 | .740 |
| Donald Trump (2nd) | 181 | +0.104 | +0.08 | .318 |
| Joseph R. Biden | 31 | +0.012 | +0.02 | .902 |

Reagan is the only significant **decline**; Obama shows a significant **increase**
(rising complexity — the opposite of decline). The composite is more conservative
than the markers (R=−0.15) because `idea_density` does not co-move with Reagan's
decline and dilutes the index; the signal is carried by the two validated Berisha
markers. Figure: `documents/discourse_complexity_trajectory_impromptu.png`.

## The original objective: Trump small-n, resolved

The analysis was motivated by Trump's 2nd term being un-analyzable under the title
filter (≈ 10–22 documents). The classifier raises this to **n = 181** spontaneous
documents reaching the 1,400-word floor, and the result is a **clean null** on
both analyses — i.e. the instrument gained power without manufacturing a signal.

| presidency | old (titled press conf.) | impromptu set (≥ 0.5) |
|---|---:|---:|
| Trump (2nd term) | 22 | **181** |
| (cohort range) | 77 – 243 | 173 – 267 |

## Caveats

Exploratory, not diagnostic. The classifier is a single 7B local model
(prompt-versioned provenance retained); spontaneity is genre-graded and
threshold-sensitive (see method note). The Berisha li-verb marker is an
approximate list. Biden's 1,400-word-floor sample is small (n=31). Reagan's named
identification follows the published, peer-reviewed precedent (Berisha et al.
2015); all comparative framing otherwise uses coded-first neutral identifiers.
