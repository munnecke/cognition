"""
cohort_figures.py — visualize the Berisha-style longitudinal trend across the
whole cohort of presidencies.

Produces two figures (using neutral identifiers, "coded first"):
  documents/cohort_<feature>_grid.png     small multiples — one panel per presidency
  documents/cohort_<feature>_overlay.png  one plot — OLS trend lines on normalized time

Usage:  python scripts/cohort_figures.py [unique_words|ns_plus_fillers]
"""

from __future__ import annotations

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import common as C
import replicate_berisha as R

# Complete presidencies (Trump still collecting, Biden not yet).
KEYS = ["reagan", "bush41", "clinton", "bush43", "obama"]
LABELS = {"unique_words": "unique words (first 1,400)",
          "ns_plus_fillers": "non-specific nouns + fillers"}


def gather(feature: str):
    out = []
    for k in KEYS:
        rows = R.collect_conferences(k, 1400)
        if not rows:
            continue
        y = np.array([r[feature] for r in rows], dtype=float)
        x = np.arange(len(rows))
        keep = np.abs(y - y.mean()) <= 2 * y.std()      # same >2 SD drop as the stats
        out.append({
            "code": C.neutral_code(k), "x": x[keep], "y": y[keep],
            "res": R.regress(rows, feature),
            "span": f"{rows[0]['date'][:4]}–{rows[-1]['date'][:4]}", "n": len(rows),
        })
    return out


def grid(series, feature: str, out: str):
    flabel = LABELS[feature]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharey=True)
    axes = axes.ravel()
    for ax, s in zip(axes, series):
        ax.scatter(s["x"], s["y"], s=20, color="#33506b", alpha=0.55, edgecolor="none")
        m, b = np.polyfit(s["x"], s["y"], 1)
        xs = np.array([s["x"].min(), s["x"].max()])
        ax.plot(xs, m * xs + b, color="#b22222", lw=2, ls="--")
        sig = "*" if s["res"]["p"] < 0.05 else ""
        ax.set_title(f"President {s['code']}  ({s['span']})", fontsize=11)
        ax.text(0.96, 0.06, f"R={s['res']['R']:+.3f} p={s['res']['p']:.3f}{sig}",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc"))
        ax.grid(True, alpha=0.25)
        ax.set_xlabel("news conference (chronological)", fontsize=8)
    for ax in axes[len(series):]:
        ax.axis("off")
    axes[0].set_ylabel(flabel)
    if len(axes) > 3:
        axes[3].set_ylabel(flabel)
    fig.suptitle(f"{flabel} over each presidency — news-conference answers (Berisha-style)\n"
                 "neutral identifiers; dashed = OLS trend; * significant at p<0.05", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def overlay(series, feature: str, out: str):
    flabel = LABELS[feature]
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    for i, s in enumerate(series):
        denom = s["x"].max() if s["x"].max() > 0 else 1
        xn = s["x"] / denom                              # normalize time to [0,1]
        m, b = np.polyfit(xn, s["y"], 1)
        sig = "*" if s["res"]["p"] < 0.05 else ""
        ax.plot([0, 1], [b, m + b], lw=2.6, color=colors[i],
                label=f"President {s['code']}  ({s['res']['R']:+.2f}{sig})")
    ax.set_xlabel("term progress  (first → last news conference)")
    ax.set_ylabel(flabel)
    ax.set_title(f"{flabel}: trend per presidency (OLS, normalized time)\n"
                 "neutral identifiers; * significant at p<0.05")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def main():
    feature = sys.argv[1] if len(sys.argv) > 1 else "unique_words"
    series = gather(feature)
    grid(series, feature, f"documents/cohort_{feature}_grid.png")
    overlay(series, feature, f"documents/cohort_{feature}_overlay.png")


if __name__ == "__main__":
    main()
