"""
cohort_figures.py — Berisha-style longitudinal news-conference charts for the
whole cohort of presidencies.

Reproduces the figure style of Berisha et al. (2015) Figure 1 (a metric over
chronological news conferences, with an OLS trend), but extended to every
presidency. Two metrics, the two the paper found significant for Reagan:
unique words and non-specific nouns + fillers.

For each metric it writes:
  documents/cohort_<metric>_grid.png      small multiples — one panel per presidency
  documents/cohort_<metric>_overlay.png   one plot — OLS trend lines on normalized time

Labels default to full names (--labels codes for the neutral identifiers).
Trump's two terms are split by date (2021-01-20).

Usage:  python scripts/cohort_figures.py [--labels names|codes] [metric ...]
"""

from __future__ import annotations

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import common as C
import replicate_berisha as R

# (president key, full label, neutral code, date_lo, date_hi)  — lo/hi split Trump's terms
PRESIDENCIES = [
    ("reagan",  "Ronald Reagan",           "K", None,         None),
    ("bush41",  "George H. W. Bush",       "M", None,         None),
    ("clinton", "Bill Clinton",            "N", None,         None),
    ("bush43",  "George W. Bush",          "H", None,         None),
    ("obama",   "Barack Obama",            "P", None,         None),
    ("trump",   "Donald Trump (1st term)", "S", None,         "2021-01-20"),
    ("trump",   "Donald Trump (2nd term)", "V", "2021-01-20", None),
    ("biden",   "Joseph R. Biden",         "L", None,         None),
]
METRICS = {"unique_words": "unique words (first 1,400)",
           "ns_plus_fillers": "non-specific nouns + fillers"}


def gather(metric: str, use_names: bool):
    out = []
    for key, name, code, lo, hi in PRESIDENCIES:
        rows = [r for r in R.collect_conferences(key, 1400)
                if (lo is None or r["date"] >= lo) and (hi is None or r["date"] < hi)]
        if not rows:
            continue
        y = np.array([r[metric] for r in rows], dtype=float)
        x = np.arange(len(rows))
        keep = np.abs(y - y.mean()) <= 2 * y.std()
        out.append({
            "label": name if use_names else f"President {code}",
            "x": x[keep], "y": y[keep], "res": R.regress(rows, metric),
            "span": f"{rows[0]['date'][:4]}–{rows[-1]['date'][:4]}", "n": len(rows),
        })
    return out


def grid(series, metric: str, out: str):
    flabel = METRICS[metric]
    n = len(series)
    cols = 4
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.0 * rows), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, s in zip(axes, series):
        ax.scatter(s["x"], s["y"], s=16, color="#33506b", alpha=0.55, edgecolor="none")
        if len(s["x"]) >= 2:
            m, b = np.polyfit(s["x"], s["y"], 1)
            xs = np.array([s["x"].min(), s["x"].max()])
            ax.plot(xs, m * xs + b, color="#b22222", lw=2, ls="--")
        sig = "*" if s["res"]["p"] < 0.05 else ""
        ax.set_title(f"{s['label']}\n({s['span']}, n={s['n']})", fontsize=9.5)
        ax.text(0.96, 0.05, f"R={s['res']['R']:+.2f} p={s['res']['p']:.3f}{sig}",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#ccc"))
        ax.grid(True, alpha=0.25)
        ax.tick_params(labelsize=8)
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle(f"{flabel} over time, by presidency — news-conference answers "
                 "(Berisha-style)\ndashed = OLS trend; * significant at p<0.05", fontsize=12)
    fig.supxlabel("news conference (chronological)", fontsize=9)
    fig.tight_layout(rect=[0, 0.01, 1, 0.95])
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def overlay(series, metric: str, out: str):
    flabel = METRICS[metric]
    fig, ax = plt.subplots(figsize=(10, 6.5))
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    for i, s in enumerate(series):
        if len(s["x"]) < 2:
            continue
        xn = s["x"] / (s["x"].max() or 1)
        m, b = np.polyfit(xn, s["y"], 1)
        sig = "*" if s["res"]["p"] < 0.05 else ""
        ax.plot([0, 1], [b, m + b], lw=2.4, color=colors[i % 10],
                label=f"{s['label']} ({s['res']['R']:+.2f}{sig})")
    ax.set_xlabel("term progress (first → last news conference)")
    ax.set_ylabel(flabel)
    ax.set_title(f"{flabel}: trend per presidency (OLS, normalized time)\n"
                 "* significant at p<0.05")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def main():
    args = sys.argv[1:]
    use_names = True
    if "--labels" in args:
        i = args.index("--labels")
        use_names = args[i + 1] != "codes"
        del args[i:i + 2]
    metrics = args or list(METRICS)
    for metric in metrics:
        series = gather(metric, use_names)
        grid(series, metric, f"documents/cohort_{metric}_grid.png")
        overlay(series, metric, f"documents/cohort_{metric}_overlay.png")


if __name__ == "__main__":
    main()
