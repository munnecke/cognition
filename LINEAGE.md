# Intellectual lineage — evolutionary attribution of an idea

This project is **completely open**: anyone may validate, reuse, or extend it as
they see fit. In the spirit of Douglas Engelbart's vision of *dynamic knowledge
repositories* — where knowledge is a living, granularly-linked structure that
co-evolves with the community working on it — we keep an explicit, version-
controlled genealogy of the idea rather than a static citation list.

- **Ancestors** = prior work this stands on.
- **Descendants** = work that extends, applies, or refutes it.
- The git history itself is the audit trail: every change is attributed, timestamped, and public.

**To attach your work to this lineage**, open a pull request or issue adding an
entry below (template at the bottom). Cite this repository (see `CITATION.cff`),
and — equally important — register your contribution here so the next person
inherits the full chain, forward and backward.

---

## This node

- **id:** `presidential-cognition-corpus`
- **what:** an open, validated pipeline for longitudinal linguistic / cognitive-linguistic
  analysis of U.S. presidential *spoken* language (Reagan → present)
- **canonical:** https://github.com/munnecke/cognition
- **established:** 2026-06
- **status:** active; methods validated by independent replication of Berisha et al. (2015)

---

## Ancestors

> Work this project builds on, nearest parent first.

- **Berisha, Wang, LaCross & Liss (2015)** — *Tracking Discourse Complexity
  Preceding Alzheimer's Disease Diagnosis* (J Alzheimers Dis 45(3):959–963,
  doi:10.3233/JAD-142763). **Direct parent / replication target** — the news-
  conference method this project independently reproduces and generalizes.
- **Le, Lancashire, Hirst & Jokel (2011)** — longitudinal lexical/syntactic
  decline in the writing of British novelists (Lit Linguist Comput 26). Method
  ancestor for longitudinal lexical-trend detection.
- **Snowdon et al. (1996), the "Nun Study"** — early-life linguistic ability and
  late-life cognition (JAMA 275:528–532). Foundational evidence linking language
  complexity to cognitive trajectory.
- **Bird, Lambon Ralph, Patterson & Hodges (2000)** — frequency/imageability of
  nouns and verbs in semantic dementia (Brain Lang 73). Source of the low-
  imageability-verb feature.
- **Gottschalk, Uliana & Gilbert (1988)** — cognitive impairment inferred from
  presidential candidates' campaign-debate behavior (Public Admin Rev). Early
  precedent for analyzing political speech for cognitive markers.
- **Pennebaker (function-word / pronoun analysis)** — psychological and cognitive
  signal in closed-class words; motivates the pronoun and function-word features.
- **Engelbart (1962)** — *Augmenting Human Intellect: A Conceptual Framework*. The
  meta-ancestor: the practice of evolutionary, attributed, collaboratively-curated
  knowledge that this LINEAGE.md file itself enacts.
- **American Presidency Project** (Woolley & Peters, UC Santa Barbara) — the
  primary archival data source.

---

## Descendants

> Work that extends, applies, refutes, or re-uses this. **Add yours here.**

- *(open — be the first)*

*Aspirational examples of the kind of extension this enables (not yet realized):*
- *Clinical evaluation of ambient recordings of patient–clinician interaction —
  applying the longitudinal spontaneous-speech method to consented clinical
  settings for early cognitive screening.*
- *Cross-national extension to other heads of state / public figures with long
  spoken-record archives.*
- *Adversarial / null-model robustness studies of longitudinal speech trends.*

---

## Entry template

Copy this into the relevant section in a pull request:

```
- **Authors (Year)** — *Title*. Venue / link / DOI.
  Relation: ancestor | descendant | sibling.
  Relationship: <one or two sentences — how it connects to this node>.
  Added by: <name>, <date>.
```
