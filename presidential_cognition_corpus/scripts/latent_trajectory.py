"""
latent_trajectory.py — within-person trajectory of a latent "cognitive-linguistic
integrity" construct, in the validated Berisha news-conference frame.

This is the multi-indicator upgrade of the Berisha replication. Instead of tracking
one marker, we build a composite from several decline-relevant indicators and ask
whether it drifts within a president over time:

  indicators (per news conference, president's first-1400-word spontaneous answers):
    unique_words   (Lancaster-stemmed)         higher = more intact
    idea_density   (CPIDR-style propositions)  higher = more intact
    ns_plus_fillers (non-specific nouns + fillers)  higher = LESS intact (negated)

  integrity = mean( z(unique), z(idea), -z(ns_plus_fillers) )   higher = more intact

Each indicator is z-scored across the pooled cohort, sign-aligned, averaged. Then,
within each president, integrity is regressed against chronological index (with the
same >2 SD outlier drop as Berisha). A significant DECLINE in a known-AD case
(Reagan) and flat controls is the latent-construct version of the published result.

Exploratory & preliminary (5 complete presidents; Trump S/V + Biden L pending).
Coded-first. Usage: python scripts/latent_trajectory.py
"""

from __future__ import annotations

import glob
import re

import numpy as np
import pandas as pd
import spacy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
import replicate_berisha as R
import segment_speaker as S

KEYS = ["reagan", "bush41", "clinton", "bush43", "obama"]
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
            if ind:
                rows.append({"key": k, "date": m.group(1) if m else "",
                             "unique": ind[0], "ns_fill": ind[1], "idea": ind[2]})
    df = pd.DataFrame(rows).sort_values(["key", "date"]).reset_index(drop=True)
    for col in ["unique", "ns_fill", "idea"]:
        df["z_" + col] = (df[col] - df[col].mean()) / df[col].std()
    df["integrity"] = (df["z_unique"] + df["z_idea"] - df["z_ns_fill"]) / 3
    return df


def main():
    df = gather()
    print("Latent cognitive-linguistic INTEGRITY trajectory — news conferences, coded-first")
    print("(integrity = z(unique) + z(idea_density) - z(NS+fillers); higher = more intact)")
    print(f"\n{'':11} {'n':>4}   {'INTEGRITY slope':>18}   {'(unique)':>12} {'(idea)':>11} {'(NS+fill)':>12}")
    print("-" * 76)
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    for i, k in enumerate(KEYS):
        sub = df[df["key"] == k].reset_index(drop=True)
        recs = sub.to_dict("records")
        intg = R.regress(recs, "integrity")
        u = R.regress(recs, "z_unique"); idea = R.regress(recs, "idea"); nf = R.regress(recs, "ns_fill")
        code = C.neutral_code(k)
        s = lambda r: "*" if r["p"] < 0.05 else " "
        print(f"President {code}  {len(sub):>4}   R={intg['R']:+.3f} p={intg['p']:.3f}{s(intg)}   "
              f"{u['R']:+.2f}{s(u)}      {idea['R']:+.2f}{s(idea)}     {nf['R']:+.2f}{s(nf)}")
        # trajectory line (normalized time)
        y = sub["integrity"].values
        x = np.arange(len(y)); keep = np.abs(y - y.mean()) <= 2 * y.std()
        xn = x[keep] / (x[keep].max() or 1)
        m, b = np.polyfit(xn, y[keep], 1)
        ax.plot([0, 1], [b, m + b], lw=2.6, color=colors[i],
                label=f"President {code} ({intg['R']:+.2f}{s(intg).strip()})")
    print("\nDecline = negative integrity slope. Reveal:",
          {C.neutral_code(k): k for k in KEYS})
    ax.set_xlabel("term progress (first → last news conference)")
    ax.set_ylabel("cognitive-linguistic integrity (composite z)")
    ax.set_title("Latent integrity trajectory per presidency (news conferences)\n"
                 "neutral identifiers; * significant at p<0.05")
    ax.grid(True, alpha=0.3); ax.legend(loc="best", fontsize=9)
    fig.tight_layout(); fig.savefig("documents/latent_integrity_trajectory.png", dpi=150)
    print("wrote documents/latent_integrity_trajectory.png")


if __name__ == "__main__":
    main()
