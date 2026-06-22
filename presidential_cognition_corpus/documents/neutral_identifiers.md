# Neutral president identifiers

## Rationale

Following an idea associated with **Bertrand Russell**, this project uses neutral
symbolic identifiers when discussing comparative results. Russell frequently
reformulated emotionally charged political and philosophical questions using
abstract symbols or placeholders, allowing readers to examine the *structure* of
an argument before attaching ideological or personal associations. The goal was
not concealment, but reduction of unnecessary bias.

The Presidential Cognition Corpus adopts the same spirit. Public figures carry
strong historical, political, and emotional associations; referring to "President
Reagan," "President Trump," or "President Biden" can lead readers to import prior
beliefs into the interpretation of linguistic results. Neutral identifiers help
focus attention on the language itself.

**These identifiers are not anonymization.** Many analyses and historical facts
make identities obvious (e.g., discussing Reagan's later Alzheimer's diagnosis, or
the named Berisha-replication validation). They are a **methodological,
presentation-order device** — *coded first, revealed second* — to encourage
pattern recognition and reduce tribal reactions during exploratory and comparative
work, analogous to blinded analyses in other sciences. They are most valuable for
**affect / style variables** (anger, Me/Us focus, sentiment), where priming is
strongest.

## Letter choice

Identifiers deliberately avoid letters with strong cultural associations: **A** and
**F** (grades), **X** ("unknown"), **Z** ("sleepy"), **Q** (contemporary political
associations), **T** (a Trump monogram), **R** (Reagan / "Republican" ballot
letter), and **W / G** (the Bushes). The remaining letters are visually distinct,
easy to remember, and relatively free of emotional baggage. Assignments are
**arbitrary and fixed**, and chosen so that no letter matches its president's
initial (so the letter itself does not leak the name).

## The mapping

Trump's two **non-consecutive terms are treated as separate presidencies** — the
four-year gap may itself reveal a longitudinal change in linguistic capability, so
they are split (by date, at 2021-01-20) rather than merged.

| Presidency | Years | Identifier |
|---|---|---|
| Reagan | 1981–1989 | **President K** |
| G.H.W. Bush | 1989–1993 | **President M** |
| Clinton | 1993–2001 | **President N** |
| G.W. Bush | 2001–2009 | **President H** |
| Obama | 2009–2017 | **President P** |
| Trump (1st term) | 2017–2021 (incl. 2015–16 campaign) | **President S** |
| Trump (2nd term) | 2021– (incl. campaign) → 2025– | **President V** |
| Biden | 2021–2025 | **President L** |

## Use in the project

- **Default to codes** in comparative and affect-variable outputs (dashboards,
  new figures, cross-president tables) — show the pattern, then reveal identity.
- **Real names where the science requires them** — the Berisha replication (which
  reproduces a *published* study about Reagan and Bush by name), discussion of
  Reagan's Alzheimer's, and any historically specific claim.
- Implemented in `scripts/common.py`: `neutral_code(president_key, date)` and
  `neutral_label(...)`, with `CODE_TO_PRESIDENT` for the reveal/legend.
