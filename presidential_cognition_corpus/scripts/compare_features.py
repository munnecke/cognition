"""
compare_features.py — cross-president comparison of linguistic / affect features.

Joins linguistic_features.csv to metadata, groups by NEUTRAL IDENTIFIER
("coded first"), and reports per-president means for the style/affect variables
where de-biasing matters most. Trump's two terms are separate codes (S / V).

Prints a coded table and writes a coded figure (documents/cross_president_features.png).
NOTE: aggregates across all spoken genres (inaugurals, remarks, news conferences,
…), so this is a broad stylistic comparison, not a genre-controlled one.

Usage:  python scripts/compare_features.py
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import common as C

# (feature column, short label, higher-means)
FEATURES = [
    ("mtld", "Lexical diversity (MTLD)"),
    ("first_person_singular_ratio", "I-focus (1st-pers singular)"),
    ("first_person_plural_ratio", "We-focus (1st-pers plural)"),
    ("vader_compound", "Sentiment (VADER)"),
    ("mean_dependency_distance", "Syntactic complexity (dep. dist.)"),
]


def load() -> pd.DataFrame:
    meta = C.load_metadata()[["id", "president", "date"]]
    feats = pd.read_csv(C.DATA_CLEAN / "linguistic_features.csv", dtype=str, keep_default_na=False)
    df = meta.merge(feats, on="id", how="inner")
    for col, _ in FEATURES:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["code"] = [C.neutral_code(p, d) for p, d in zip(df["president"], df["date"])]
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("code")
    out = pd.DataFrame({"n": g.size()})
    for col, _ in FEATURES:
        out[col] = g[col].mean()
    # Me/Us focus = ratio of mean singular to mean plural (stable aggregate form)
    out["me_us"] = out["first_person_singular_ratio"] / out["first_person_plural_ratio"]
    return out.sort_index()


def print_table(s: pd.DataFrame) -> None:
    print("\nCross-president comparison (neutral identifiers, coded first)")
    print(f"{'':10} {'n':>5} {'MTLD':>7} {'I-ratio':>8} {'We-ratio':>9} "
          f"{'Me/Us':>6} {'sentiment':>10} {'dep.dist':>9}")
    print("-" * 72)
    for code, r in s.iterrows():
        print(f"President {code:1} {int(r['n']):>5} {r['mtld']:>7.1f} "
              f"{r['first_person_singular_ratio']:>8.4f} {r['first_person_plural_ratio']:>9.4f} "
              f"{r['me_us']:>6.2f} {r['vader_compound']:>10.3f} {r['mean_dependency_distance']:>9.3f}")
    print("\nLegend (reveal):", ", ".join(f"{k}={v}" for k, v in C.CODE_TO_PRESIDENT.items()
                                          if k in s.index))


def figure(s: pd.DataFrame, out: str) -> None:
    panels = [("mtld", "Lexical diversity (MTLD)"),
              ("me_us", "Me/Us focus (I : we)"),
              ("vader_compound", "Sentiment (VADER)"),
              ("mean_dependency_distance", "Syntactic complexity")]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    codes = list(s.index)
    colors = plt.cm.tab10(np.linspace(0, 1, 10))[:len(codes)]
    for ax, (col, label) in zip(axes.ravel(), panels):
        ax.bar([f"P {c}" for c in codes], s[col].values, color=colors)
        ax.set_title(label, fontsize=11)
        ax.grid(True, axis="y", alpha=0.25)
    fig.suptitle("Cross-president style / affect comparison — neutral identifiers "
                 "(coded first)\nmeans across all spoken genres", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out, dpi=150)
    print(f"\nwrote {out}")


def main():
    df = load()
    s = summarize(df)
    print_table(s)
    figure(s, "documents/cross_president_features.png")


if __name__ == "__main__":
    main()
