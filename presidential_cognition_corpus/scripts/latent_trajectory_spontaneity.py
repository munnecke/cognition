"""
latent_trajectory_spontaneity.py — the discourse-complexity LOWESS trajectory on
the LLM-selected impromptu set (spontaneity >= threshold), instead of the
title="news conference" frame.

Identical composite and method to `latent_trajectory.py` — within-person
trajectory of complexity = mean( z(unique), z(idea_density), -z(NS+fillers) ),
regressed on years-into-administration, LOWESS-smoothed — but the document set is
defined by the spontaneity classifier (llm_extractions, prompt_version=
'spontaneity-v2'). Reuses `latent_trajectory`'s indicators()/years()/PRESIDENCIES
so the only change is selection.

Threshold note (see tech journal 2026-06-24): formal news conferences score
"mixed" (~0.5) because of their prepared opening, so **0.5 is the right cut to
keep the Berisha-frame documents**; 0.7 selects a narrower exchange-only register.

Usage:  python scripts/latent_trajectory_spontaneity.py [--threshold 0.5]
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.nonparametric.smoothers_lowess import lowess
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import psycopg

import latent_trajectory as LT   # indicators(), years(), PRESIDENCIES, _nlp
import segment_speaker as S


def target_dsn(db: str) -> str:
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


def gather(conn, threshold: float) -> pd.DataFrame:
    """Same composite as latent_trajectory.gather(), but documents come from the
    spontaneity >= threshold impromptu set (president-only, first 1,400 words)."""
    sql = ("SELECT s.president_key, s.date::text, s.full_text "
           "FROM speeches s JOIN llm_extractions e ON e.speech_id = s.id "
           "WHERE s.is_canonical AND s.presidential_voice AND s.word_count >= 200 "
           "  AND e.extraction_type = 'spontaneity' "
           "  AND e.prompt_version = 'spontaneity-v2' "
           "  AND e.confidence_score >= %s "
           "ORDER BY s.date, s.id")
    rows = []
    with conn.cursor() as cur:
        cur.execute(sql, (threshold,))
        fetched = cur.fetchall()
    for key, d, body in fetched:
        ind = LT.indicators(S.president_answers(body or ""))   # None if < 1,400 answer-words
        if ind:
            rows.append({"key": key, "date": d,
                         "unique": ind[0], "ns_fill": ind[1], "idea": ind[2]})
    df = pd.DataFrame(rows)
    for col in ["unique", "ns_fill", "idea"]:
        df["z_" + col] = (df[col] - df[col].mean()) / df[col].std()
    df["complexity"] = (df["z_unique"] + df["z_idea"] - df["z_ns_fill"]) / 3
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="presidential_speech")
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    with psycopg.connect(target_dsn(args.db)) as conn:
        df = gather(conn, args.threshold)

    print(f"DISCOURSE COMPLEXITY trajectory — impromptu set (spontaneity >= {args.threshold}), "
          "regressed on years")
    print("(complexity = z(unique) + z(idea_density) - z(NS+fillers); higher = more complex)\n")
    print(f"{'presidency':26} {'n':>3}   {'slope/yr':>9}   {'R':>7} {'p':>7}")
    print("-" * 62)

    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    colors = plt.cm.tab10(np.linspace(0, 1, 10))
    for i, (key, name, short, lo, hi, start) in enumerate(LT.PRESIDENCIES):
        s = df[df["key"] == key]
        if lo is not None:
            s = s[s["date"] >= lo]
        if hi is not None:
            s = s[s["date"] < hi]
        s = s.sort_values("date")
        if len(s) < 3:
            print(f"{name:26} {len(s):>3}   (too few)")
            continue
        x = np.array([LT.years(d, start) for d in s["date"]])
        y = s["complexity"].values
        keep = np.abs(y - y.mean()) <= 2 * y.std()
        xk, yk = x[keep], y[keep]
        r, p = stats.pearsonr(xk, yk)
        m, b = np.polyfit(xk, yk, 1)
        sig = "*" if p < 0.05 else ""
        print(f"{name:26} {len(s):>3}   {m:>+8.3f}   {r:>+6.2f} {p:>7.3f}{sig}")
        order = np.argsort(xk)
        sm = lowess(yk[order], xk[order], frac=0.7, return_sorted=True)
        ax.plot(sm[:, 0], sm[:, 1], lw=2.4, color=colors[i % 10],
                label=f"{name} ({r:+.2f}{sig})")
        ax.text(sm[-1, 0] + 0.1, sm[-1, 1], f"{short}{sig}", fontsize=8.5, va="center",
                color=colors[i % 10], fontweight="bold")
    ax.set_xlim(-0.3, 10.6)
    ax.set_xlabel("years into the administration  (Trump measured from 2017, so his 2nd term sits at 8–10)")
    ax.set_ylabel("discourse complexity index (composite z)")
    ax.set_title(f"Discourse complexity over each administration — impromptu set "
                 f"(spontaneity ≥ {args.threshold})\nLOWESS-smoothed; R / * = overall linear trend (p<0.05)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False)
    fig.tight_layout()
    out = "documents/discourse_complexity_trajectory_impromptu.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
