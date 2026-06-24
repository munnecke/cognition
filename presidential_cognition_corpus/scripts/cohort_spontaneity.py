"""
cohort_spontaneity.py — Berisha markers per presidency on the LLM-selected
*impromptu* set (spontaneity >= threshold), instead of the title="news
conference" filter.

Same validated method as replicate_berisha / cohort_figures — president-only
spontaneous answers (segment_speaker), first 1,400 words, unique-words and
non-specific-nouns+fillers, Pearson vs chronological index with >2 SD outlier
removal — but the document set is now defined by the spontaneity classifier
(llm_extractions, prompt_version='spontaneity-v2'). This is the payoff of the
classifier: a bigger, genre-diverse spontaneous sample (interviews, town halls,
exchanges, off-the-cuff remarks), not just formal news conferences.

The selection swap is the ONLY change from the validated replication; if Reagan
still uniquely shows the decline signature here, it holds on a much larger and
fairer sample.

Usage:  python scripts/cohort_spontaneity.py [--threshold 0.7] [--no-figure]
"""

from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import psycopg

import common as C
import replicate_berisha as R
import segment_speaker as S

# (key, full label, neutral code, date_lo, date_hi) — lo/hi split Trump's terms
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


def target_dsn(db: str) -> str:
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


def collect_spontaneous(conn, president, threshold, max_words, lo, hi):
    """Chronological Berisha-feature rows for a president's impromptu set.

    Selection: canonical, presidential_voice, >=200 words, spontaneity>=threshold,
    in the optional [lo, hi) date window. Then the SAME president-only
    segmentation + 1,400-word floor as the validated replication.
    """
    where = ["s.is_canonical", "s.presidential_voice", "s.word_count >= 200",
             "s.president_key = %s", "e.extraction_type = 'spontaneity'",
             "e.prompt_version = 'spontaneity-v2'", "e.confidence_score >= %s"]
    params = [president, threshold]
    if lo:
        where.append("s.date >= %s"); params.append(lo)
    if hi:
        where.append("s.date < %s"); params.append(hi)
    sql = ("SELECT s.id, s.date::text, s.full_text FROM speeches s "
           "JOIN llm_extractions e ON e.speech_id = s.id "
           "WHERE " + " AND ".join(where) + " ORDER BY s.date, s.id")
    rows = []
    with conn.cursor() as cur:
        cur.execute(sql, params)
        fetched = cur.fetchall()
    for sid, date, body in fetched:
        ans = S.president_answers(body or "")
        feats = R.berisha_features(ans, max_words)   # None if < 1,400 answer-words
        if feats is None:
            continue
        feats["date"] = date
        rows.append(feats)
    rows.sort(key=lambda r: r["date"])
    return rows


def gather(conn, threshold, max_words):
    out = []
    for key, name, code, lo, hi in PRESIDENCIES:
        rows = collect_spontaneous(conn, key, threshold, max_words, lo, hi)
        if len(rows) < 3:
            out.append({"label": name, "n": len(rows), "rows": rows,
                        "span": "", "res": {}})
            continue
        res = {m: R.regress(rows, m) for m in METRICS}
        out.append({"label": name, "n": len(rows), "rows": rows,
                    "span": f"{rows[0]['date'][:4]}–{rows[-1]['date'][:4]}", "res": res})
    return out


def print_table(series, threshold):
    print(f"\nBerisha markers on the impromptu set (spontaneity >= {threshold}, "
          "president-only answers, first 1,400 words)\n")
    hdr = f"{'presidency':<26}{'n':>4}  {'span':<11}"
    for m in METRICS:
        hdr += f"{m:>22}"
    print(hdr)
    print(f"{'':<26}{'':>4}  {'':<11}" + "        R      p        R      p")
    for s in series:
        line = f"{s['label']:<26}{s['n']:>4}  {s['span']:<11}"
        if s["res"]:
            for m in METRICS:
                r = s["res"][m]
                sig = "*" if r["p"] < 0.05 else " "
                line += f"   {r['R']:+5.2f} {r['p']:6.3f}{sig}"
        else:
            line += "   (n<3 — skipped)"
        print(line)
    print("\n* p<0.05.  Decline signature = unique_words R<0 AND ns_plus_fillers R>0, "
          "both significant.")


def grid(series, metric, threshold, out):
    flabel = METRICS[metric]
    panels = [s for s in series if s["res"]]
    cols, n = 4, len(panels)
    nrows = (n + cols - 1) // cols
    fig, axes = plt.subplots(nrows, cols, figsize=(3.2 * cols, 3.0 * nrows), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, s in zip(axes, panels):
        y = np.array([r[metric] for r in s["rows"]], dtype=float)
        x = np.arange(len(y))
        keep = np.abs(y - y.mean()) <= 2 * y.std()
        xk, yk = x[keep], y[keep]
        ax.scatter(xk, yk, s=12, color="#33506b", alpha=0.45, edgecolor="none")
        if len(xk) >= 2:
            m, b = np.polyfit(xk, yk, 1)
            xs = np.array([xk.min(), xk.max()])
            ax.plot(xs, m * xs + b, color="#b22222", lw=2, ls="--")
        r = s["res"][metric]
        sig = "*" if r["p"] < 0.05 else ""
        ax.set_title(f"{s['label']}\n({s['span']}, n={s['n']})", fontsize=9.5)
        ax.text(0.96, 0.05, f"R={r['R']:+.2f} p={r['p']:.3f}{sig}",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#ccc"))
        ax.grid(True, alpha=0.25); ax.tick_params(labelsize=8)
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle(f"{flabel} over time — impromptu set (spontaneity ≥ {threshold}), "
                 "president-only answers\ndashed = OLS trend; * p<0.05", fontsize=12)
    fig.supxlabel("impromptu transcript (chronological)", fontsize=9)
    fig.tight_layout(rect=[0, 0.01, 1, 0.95])
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="presidential_speech")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--max-words", type=int, default=1400)
    ap.add_argument("--no-figure", action="store_true")
    args = ap.parse_args()

    with psycopg.connect(target_dsn(args.db)) as conn:
        series = gather(conn, args.threshold, args.max_words)
    print_table(series, args.threshold)
    if not args.no_figure:
        for metric in METRICS:
            grid(series, metric, args.threshold,
                 f"{C.ROOT}/documents/impromptu_{metric}_grid.png")


if __name__ == "__main__":
    main()
