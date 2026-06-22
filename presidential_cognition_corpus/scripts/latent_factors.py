"""
latent_factors.py — exploratory latent-factor analysis of the linguistic markers.

Asks: are there underlying factors whose variation organizes the surface features?
Runs factor analysis (varimax) two ways, which answer two different questions:

  POOLED        — across all speeches. Recovers the dominant axes of variation,
                  which are mostly BETWEEN-person style + genre (the loud signal).
  WITHIN-PERSON — features centered within each president (deviations from that
                  president's own mean), so between-person differences are removed.
                  These are the axes along which a person VARIES over their corpus —
                  much closer to the drift/change signal that a latent "cognitive"
                  factor would live in.

Exploratory and preliminary (whatever presidents currently have features).
Coded-first: per-president factor means use the neutral identifiers.

Usage:  python scripts/latent_factors.py [n_factors]
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA, FactorAnalysis

import common as C

FEATS = [
    "mtld", "mattr_50", "hapax_ratio",
    "first_person_singular_ratio", "first_person_plural_ratio",
    "noun_ratio", "verb_ratio", "adjective_ratio", "adverb_ratio", "function_word_ratio",
    "mean_dependency_distance", "mean_tree_depth", "subordination_ratio", "clauses_per_sentence",
    "indefinite_noun_ratio", "hedge_ratio", "filler_ratio", "vader_compound",
]
# add idea_density automatically if present in the data
OPTIONAL = ["idea_density"]


def load() -> tuple[pd.DataFrame, list[str]]:
    meta = C.load_metadata()[["id", "president", "date"]]
    feats = pd.read_csv(C.DATA_CLEAN / "linguistic_features.csv", dtype=str, keep_default_na=False)
    cols = FEATS + [c for c in OPTIONAL if c in feats.columns]
    df = meta.merge(feats, on="id", how="inner")
    for f in cols:
        df[f] = pd.to_numeric(df[f], errors="coerce")
    df = df.dropna(subset=cols)
    df["code"] = [C.neutral_code(p, d) for p, d in zip(df["president"], df["date"])]
    return df, cols


def top_loadings(components: np.ndarray, cols: list[str], k: int = 5) -> None:
    for i, comp in enumerate(components):
        order = np.argsort(-np.abs(comp))[:k]
        parts = [f"{'+' if comp[j] >= 0 else '-'}{cols[j]}({comp[j]:+.2f})" for j in order]
        print(f"  Factor {i + 1}:  " + "  ".join(parts))


def run(n_factors: int) -> None:
    df, cols = load()
    print(f"n speeches: {len(df)} | features: {len(cols)} | presidents: "
          f"{sorted(df['code'].unique())}")
    X = df[cols].values

    # dimensionality sense-check
    evr = PCA().fit(StandardScaler().fit_transform(X)).explained_variance_ratio_
    print(f"\nPCA variance explained (first 6 PCs): "
          f"{', '.join(f'{v:.0%}' for v in evr[:6])}  (cumulative "
          f"{np.cumsum(evr[:n_factors])[-1]:.0%} in {n_factors})")

    # ---- POOLED ----
    Xs = StandardScaler().fit_transform(X)
    fa = FactorAnalysis(n_components=n_factors, rotation="varimax", max_iter=3000, random_state=0).fit(Xs)
    print("\n=== POOLED factors (mostly between-person style / genre) ===")
    top_loadings(fa.components_, cols)
    scores = pd.DataFrame(fa.transform(Xs), columns=[f"F{i+1}" for i in range(n_factors)])
    scores["code"] = df["code"].values
    print("\n  per-president mean factor score (coded first):")
    means = scores.groupby("code").mean().round(2)
    print(means.to_string())

    # ---- WITHIN-PERSON ----
    Xw = X - df.groupby("president")[cols].transform("mean").values
    Xws = StandardScaler().fit_transform(Xw)
    faw = FactorAnalysis(n_components=n_factors, rotation="varimax", max_iter=3000, random_state=0).fit(Xws)
    print("\n=== WITHIN-PERSON factors (axes a president varies along — the drift signal) ===")
    top_loadings(faw.components_, cols)

    print("\nReveal:", {C.neutral_code(k): k for k in
                        ["reagan", "bush41", "clinton", "bush43", "obama", "biden"]
                        if C.neutral_code(k) in df["code"].unique()})


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    run(n)


if __name__ == "__main__":
    main()
