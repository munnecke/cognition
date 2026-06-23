"""
latent_trajectory.py — within-person trajectory of a composite DISCOURSE COMPLEXITY
index, in the validated Berisha news-conference frame.

The multi-indicator upgrade of the Berisha replication. Instead of tracking one
marker, we build a composite from several decline-relevant indicators and ask
whether it drifts within a president over time:

  indicators (per news conference, president's first-1400-word spontaneous answers):
    unique_words   (Lancaster-stemmed)              higher = more complex/intact
    idea_density   (CPIDR-style propositions/word)  higher = more complex/intact
    ns_plus_fillers (non-specific nouns + fillers)  higher = LESS complex (negated)

  complexity = mean( z(unique), z(idea), -z(ns_plus_fillers) )

Each indicator is z-scored across the pooled cohort, sign-aligned, averaged. Then,
within each presidency, the index is regressed against TIME (years into the
administration), so the slope is a real per-year rate, comparable across 4- and
8-year terms. >2 SD outliers dropped (as in Berisha).

All 8 presidencies (Trump's terms split). Full names; lines labelled for print.
Usage: python scripts/latent_trajectory.py
"""

from __future__ import annotations

import glob
import re
from datetime import date

import numpy as np
import pandas as pd
import spacy
from scipy import stats
from statsmodels.nonparametric.smoothers_lowess import lowess
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
import replicate_berisha as R
import segment_speaker as S

KEYS = ["reagan", "bush41", "clinton", "bush43", "obama", "trump", "biden"]
# (key, full label, short label, date_lo, date_hi, term_start)
PRESIDENCIES = [
    ("reagan",  "Ronald Reagan",           "Reagan",     None,         None,         "1981-01-20"),
    ("bush41",  "George H. W. Bush",       "GHW Bush",   None,         None,         "1989-01-20"),
    ("clinton", "Bill Clinton",            "Clinton",    None,         None,         "1993-01-20"),
    ("bush43",  "George W. Bush",          "GW Bush",    None,         None,         "2001-01-20"),
    ("obama",   "Barack Obama",            "Obama",      None,         None,         "2009-01-20"),
    ("trump",   "Donald Trump (1st term)", "Trump '17",  None,         "2021-01-20", "2017-01-20"),
    ("trump",   "Donald Trump (2nd term)", "Trump '25",  "2021-01-20", None,         "2017-01-20"),
    ("biden",   "Joseph R. Biden",         "Biden",      None,         None,         "2021-01-20"),
]
PROP = {"VERB", "ADJ", "ADV", "ADP", "CCONJ", "SCONJ"}
_nlp = spacy.load("en_core_web_sm", disable=["parser", "ner", "lemmatizer"])


def indicators(answer_text: str, n: int = 1400):
    words = R._WORD.findall(answer_text.lower())
    if len(words) < n:
        return None
    words = words[:n]
    unique = len({R._STEM.stem(w) for w in words})
    ns_fill = sum(1 for w in words if "thing" in w) + sum(1 for w in words if w in R.FILLERS)
    doc = _nlp(" ".join(words))
    alpha = [t for t in doc if t.is_alpha]
    idea = sum(1 for t in alpha if t.pos_ in PROP) / len(alpha) if alpha else 0.0
    return unique, ns_fill, idea


def gather() -> pd.DataFrame:
    rows = []
    for k in KEYS:
        for path in sorted(glob.glob(f"{C.SPEECHES}/*_{k}_*news-conference*.txt")):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", path)
            body = "\n".join(l for l in open(path, encoding="utf-8", errors="replace").read().split("\n")
                             if not l.startswith("#"))
            ind = indicators(S.president_answers(body))
            if ind and m:
                rows.append({"key": k, "date": m.group(1),
                             "unique": ind[0], "ns_fill": ind[1], "idea": ind[2]})
    df = pd.DataFrame(rows)
    for col in ["unique", "ns_fill", "idea"]:
        df["z_" + col] = (df[col] - df[col].mean()) / df[col].std()
    df["complexity"] = (df["z_unique"] + df["z_idea"] - df["z_ns_fill"]) / 3
    return df


def years(d_iso: str, start_iso: str) -> float:
    return (date.fromisoformat(d_iso) - date.fromisoformat(start_iso)).days / 365.25


def main():
    df = gather()
    print("DISCOURSE COMPLEXITY index trajectory — news conferences (regressed on years)")
    print("(complexity = z(unique) + z(idea_density) - z(NS+fillers); higher = more complex)\n")
    print(f"{'presidency':26} {'n':>3}   {'slope/yr':>9}   {'R':>7} {'p':>7}")
    print("-" * 62)
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    xmax = 0
    for i, (key, name, short, lo, hi, start) in enumerate(PRESIDENCIES):
        s = df[df["key"] == key]
        if lo is not None:
            s = s[s["date"] >= lo]
        if hi is not None:
            s = s[s["date"] < hi]
        s = s.sort_values("date")
        if len(s) < 3:
            print(f"{name:26} {len(s):>3}   (too few)")
            continue
        x = np.array([years(d, start) for d in s["date"]])
        y = s["complexity"].values
        keep = np.abs(y - y.mean()) <= 2 * y.std()
        xk, yk = x[keep], y[keep]
        r, p = stats.pearsonr(xk, yk)
        m, b = np.polyfit(xk, yk, 1)
        sig = "*" if p < 0.05 else ""
        print(f"{name:26} {len(s):>3}   {m:>+8.3f}   {r:>+6.2f} {p:>7.3f}{sig}")
        # LOWESS-smoothed curve over the actual points (gentle frac; near-linear at small n)
        order = np.argsort(xk)
        sm = lowess(yk[order], xk[order], frac=0.7, return_sorted=True)
        ax.plot(sm[:, 0], sm[:, 1], lw=2.4, color=colors[i % 10],
                label=f"{name} ({r:+.2f}{sig})")
        ax.text(sm[-1, 0] + 0.1, sm[-1, 1], f"{short}{sig}", fontsize=8.5, va="center",
                color=colors[i % 10], fontweight="bold")
    ax.set_xlim(-0.3, 10.6)
    ax.set_xlabel("years into the administration  (Trump measured from 2017, so his 2nd term sits at 8–10)")
    ax.set_ylabel("discourse complexity index (composite z)")
    ax.set_title("Discourse complexity over each administration — news-conference answers\n"
                 "LOWESS-smoothed; R / * = overall linear trend (p<0.05)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig("documents/discourse_complexity_trajectory.png", dpi=150, bbox_inches="tight")
    print("\nwrote documents/discourse_complexity_trajectory.png")


if __name__ == "__main__":
    main()
