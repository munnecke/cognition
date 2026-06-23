# Data Dictionary — Presidential Cognition Corpus

Every field we store, with a **technical** definition (what the code computes /
the column type) and a **plain-English** meaning (what it tells you about the
speech). Three layers, kept deliberately separate:

1. **`speeches`** — one row per transcript: metadata + the raw text. The durable
   catalogue.
2. **`linguistic_features`** — deterministic, reproducible NLP measures (spaCy +
   rule-based). *No AI judgment* — the same text always yields the same numbers.
3. **`llm_extractions`** — interpretive signals from a local language model
   (currently the spontaneity score). Carries model + prompt provenance so a
   model change can never silently move the deterministic trend lines.

Plus **`presidents`**, a small lookup table.

> Convention: for ratios, "higher = more of X." Lexical/cognitive measures are
> most meaningful on **spontaneous** speech (see `presidential_voice` and the
> spontaneity score), and word-level measures are computed **president-only**
> (reporter questions stripped by `segment_speaker.py`).

---

## `presidents` — who said it

| field | type | technical | plain meaning |
|---|---|---|---|
| `id` | int | primary key | internal number for joins |
| `key` | text | stable slug (`reagan`, `trump`, …) | short name used everywhere |
| `name` | text | full display name | "Ronald Reagan" |
| `term_start` / `term_end` | date | official term boundaries | when they held office |

---

## `speeches` — the transcript catalogue

### Identity & attribution
| field | type | technical | plain meaning |
|---|---|---|---|
| `id` | text | deterministic hash of source+url+date | unique, reproducible ID for one transcript |
| `president_id` | int | FK → `presidents.id` | which president (numeric link) |
| `president_key` | text | denormalized slug | which president (readable) |
| `date` | date | speech date | the day it was delivered |
| `year` | int | year of `date` | quick year filter |
| `title` | text | source's title | headline of the transcript |
| `location` | text | venue/place if known | where it was given |

### Provenance
| field | type | technical | plain meaning |
|---|---|---|---|
| `source` | text | `app` / `miller_center` / `whitehouse_archive` | which archive it came from (UCSB American Presidency Project, Miller Center, or the Trump/NARA White House archive) |
| `source_url` | text | original page URL | where to verify the original |
| `retrieval_date` | date | when we scraped it | data-freshness stamp |

### Classification
| field | type | technical | plain meaning |
|---|---|---|---|
| `type` | text | event type (12 values) | what kind of event — see list below |
| `campaign_or_official` | text | `campaign` / `official` / null | spoken as a candidate vs. as president |

**`type` values:** `formal_address` (scripted set-piece — inaugural, State of the
Union), `radio_address` (weekly/radio), `remarks` (general delivered remarks),
`press_conference`, `q_and_a` (question-and-answer / exchange with reporters),
`interview`, `town_hall`, `debate`, `rally`, `roundtable`, `signing_statement`,
`other` (eulogies, toasts, commencement, etc.).

### Quality & de-duplication
| field | type | technical | plain meaning |
|---|---|---|---|
| `word_count` | int | tokens in `full_text` | how long the transcript is |
| `quality_score` | real | heuristic 0–1 cleanliness score | how clean/complete the scrape looks |
| `duplicate_cluster_id` | text | shared id across near-duplicate transcripts | groups copies of the same speech |
| `is_canonical` | bool | the one kept per duplicate cluster | `true` = use this copy; others are dupes (kept, not deleted) |
| `presidential_voice` | bool | `false` = not the president's spoken voice (see `flag_nonvoice.py`) | filters out third-person White House press releases (disaster declarations, appointments, Joint Statements). `true` for real speech |

### Text & search
| field | type | technical | plain meaning |
|---|---|---|---|
| `full_text` | text | normalized transcript body | the actual words spoken |
| `tsv` | tsvector | generated FTS index (`english`) | powers fast keyword search (`tsv @@ websearch_to_tsquery(...)`) |

> **For analysis, the standard filter is:**
> `is_canonical AND presidential_voice AND word_count >= 200`.

---

## `linguistic_features` — deterministic NLP (one row per speech)

Backbone: **spaCy** (`en_core_web_sm`) for part-of-speech tags + syntactic
parse, length-robust lexical-diversity measures, and **VADER** rule-based
sentiment. Promoted columns are the headline measures; the `features` JSONB holds
the complete set (superset of the columns). `spacy_model` + `extractor_version`
stamp each row so results are reproducible.

### Length
| field | type | technical | plain meaning |
|---|---|---|---|
| `n_words` | int | analyzed token count | how much text the measures are based on |
| `n_sentences`* | int | sentence count | number of sentences |

### Lexical diversity — *how varied is the vocabulary?*
| field | type | technical | plain meaning |
|---|---|---|---|
| `mtld` | real | Measure of Textual Lexical Diversity | vocabulary richness, **corrected for length** (the trustworthy one) |
| `mattr_50` | real | Moving-Average Type-Token Ratio, window 50 | same idea, measured in a sliding 50-word window |
| `type_token_ratio` | real | unique words ÷ total words | raw vocabulary variety — **length-confounded** (kept only for reference) |
| `content_ttr`* | real | TTR over content words only | variety among meaning-bearing words |
| `hapax_ratio`* | real | share of words used exactly once | how often speech reaches for a "one-off" word |

> **Why this matters:** declining lexical diversity in spontaneous speech is a
> documented early marker in the Alzheimer's literature (Berisha et al. 2015; the
> Nun Study). MTLD/MATTR are used *instead of* raw TTR because TTR falls
> artificially as text gets longer and would manufacture false trends.

### Cognitive / "discourse complexity" markers
| field | type | technical | plain meaning |
|---|---|---|---|
| `idea_density` | real | propositions (verbs, adjectives, adverbs, prepositions, conjunctions) ÷ words | how many *ideas* are packed per word; **lower** density is associated with cognitive decline (Nun Study) |
| `indefinite_noun_ratio` | real | rate of non-specific nouns ("thing," "something," "anything") | reaching for vague words instead of precise ones |
| `hedge_ratio` | real | rate of hedging terms ("maybe," "perhaps," "I think," "sort of") | tentativeness / uncertainty in phrasing |
| `filler_ratio`* | real | rate of disfluencies (`uh, um, er, ah, hmm`) | "um/uh"-type hesitations (note: curated transcripts often strip these, so values are usually low) |

### Syntactic complexity — *how intricate is the sentence structure?*
| field | type | technical | plain meaning |
|---|---|---|---|
| `mean_dependency_distance` | real | avg. distance between grammatically linked words | longer links = more complex, demanding sentences |
| `mean_tree_depth`* | real | avg. depth of the parse tree | how deeply nested the grammar is |
| `subordination_ratio` | real | subordinate clauses ÷ clauses | use of "because/although/which…" embedded clauses |
| `clauses_per_sentence`* | real | clauses ÷ sentences | how much is packed into each sentence |

### Focus / pronouns — *who is the speaker centering?*
| field | type | technical | plain meaning |
|---|---|---|---|
| `first_person_singular_ratio` | real | rate of I/me/my/mine | self-focus ("I will…") |
| `first_person_plural_ratio` | real | rate of we/us/our | collective focus ("we must…") |
| `i_to_we_ratio` | real | singular ÷ plural first-person | the **"Me vs. Us"** dial — individual vs. collective framing |

### Part-of-speech profile — *the grammatical "mix"*
(all in the `features` JSONB; rates of each tag among all words)
| field | plain meaning |
|---|---|
| `noun_ratio`*, `verb_ratio`*, `adjective_ratio`*, `adverb_ratio`*, `pronoun_ratio`* | how noun-heavy / verb-heavy / descriptive the speech is |
| `function_word_ratio`* | share of grammatical "glue" words (the, of, and, to) vs. content words |

### Sentiment (VADER) — *emotional tone*
| field | type | technical | plain meaning |
|---|---|---|---|
| `vader_compound` | real | overall sentiment, −1 (very negative) … +1 (very positive) | net positive/negative tone |
| `vader_pos`* / `vader_neu`* / `vader_neg`* | real | share of positive / neutral / negative content | the breakdown behind the compound score |

### Provenance
| field | type | meaning |
|---|---|---|
| `spacy_model` | text | which spaCy model produced the parse (e.g. `en_core_web_sm`) |
| `extractor_version` | text | version of our feature code — bump invalidates/refreshes |
| `features` | jsonb | the complete feature set (superset of the columns above) |

\* = lives in the `features` JSONB (not a promoted column).

---

## `llm_extractions` — interpretive layer (one row per speech × model × prompt)

Signals a language model judges from the text. Each row records exactly *which
model and prompt* produced it, so these never contaminate the deterministic
features. Currently one `extraction_type`: **spontaneity** (more types — affect,
evasiveness — planned).

| field | type | technical | plain meaning |
|---|---|---|---|
| `id` | bigint | row id | — |
| `speech_id` | text | FK → `speeches.id` | which transcript |
| `model` | text | LLM id (e.g. `…qwen2.5-7b-instruct…`) | which model judged it |
| `prompt_version` | text | e.g. `spontaneity-v2` | which prompt/scale version |
| `extraction_type` | text | what was measured (`spontaneity`) | the kind of signal |
| `extracted_pattern` | text | the label (`scripted` / `mixed` / `spontaneous`) | the verdict in words |
| `confidence_score` | real | for spontaneity: the **0–1 score** | how spontaneous (0 = read from a script, 1 = entirely off-the-cuff) |
| `raw` | jsonb | full model output | see below |
| `created_at` | timestamptz | when scored | provenance timestamp |

**Spontaneity `raw` JSON fields:**
| key | meaning |
|---|---|
| `spontaneity` | 0–1 score (also in `confidence_score`) |
| `label` | `scripted` / `mixed` / `spontaneous` |
| `interactive` | true if the president is answering unscripted questions |
| `reason` | one-sentence rationale from the model |
| `evidence` | a short verbatim quote supporting the call |
| `excerpt_words` | how many words of the transcript were sent to the model |

> **What spontaneity is for:** it defines the **impromptu set** —
> `spontaneity ≥ threshold` — used for the cognitive analyses, replacing the old
> brittle "title says news conference" filter. A *scripted* address reflects the
> speechwriter; only *spontaneous* speech reflects the speaker's own real-time
> language, where cognitive-linguistic markers actually live.

---

## How the layers fit together

```
speeches (catalogue + text)
   │  is_canonical AND presidential_voice AND word_count>=200   ← standard filter
   ├── linguistic_features   (deterministic: vocabulary, syntax, idea density, tone)
   └── llm_extractions       (interpretive: spontaneity → defines the impromptu set)
                                   │
        segment_speaker.py (president-only) ──► Berisha markers / trajectory analyses
```

See also: `documents/tech_journal.md` (methods + reasoning, newest first),
`documents/neutral_identifiers.md` (the coded-first president labels),
`documents/sql_recipes.md` (query examples), and `LINEAGE.md` (intellectual
ancestry of these measures).
