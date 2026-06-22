"""
build_report.py — write logs/collection_report.md summarizing the corpus.

Counts by president, year, source, and event_type, plus duplicate-cluster and
quality summaries and basic metric averages. Safe to run any time.

Usage
-----
    python build_report.py
"""

from __future__ import annotations

import common as C

LOG = C.get_logger("build_report")
REPORT = C.LOGS / "collection_report.md"


def _counts(df, col):
    if col not in df.columns:
        return []
    s = df[col].replace("", "(blank)").value_counts()
    return list(s.items())


def _md_table(pairs, headers=("value", "count")):
    if not pairs:
        return "_none_\n"
    out = [f"| {headers[0]} | {headers[1]} |", "| --- | ---: |"]
    for k, v in pairs:
        out.append(f"| {k} | {v} |")
    return "\n".join(out) + "\n"


def _avg(df, col):
    import pandas as pd
    if col not in df.columns:
        return "n/a"
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    return f"{vals.mean():.2f}" if len(vals) else "n/a"


def build() -> None:
    import pandas as pd
    df = C.load_metadata()
    n = len(df)

    lines = []
    lines.append("# Presidential Cognition Corpus — Collection Report\n")
    lines.append(f"_Generated: {C.TODAY}_\n")
    lines.append(f"**Total transcripts:** {n}\n")

    if n == 0:
        lines.append("\nNo transcripts collected yet. Run the collectors first.\n")
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        LOG.info("Empty report written to %s", REPORT)
        return

    # canonical vs duplicate
    if "is_canonical" in df.columns:
        canon = (df["is_canonical"] == "1").sum()
        dup_clusters = df[df["duplicate_cluster_id"] != ""]["duplicate_cluster_id"].nunique()
        multi = (df.groupby("duplicate_cluster_id").size() > 1).sum() if dup_clusters else 0
        lines.append(f"**Canonical transcripts:** {canon}  |  "
                     f"**Clusters:** {dup_clusters}  |  "
                     f"**Multi-member (duplicate) clusters:** {multi}\n")

    word_total = pd.to_numeric(df.get("word_count", pd.Series(dtype=str)),
                               errors="coerce").fillna(0).sum()
    lines.append(f"**Total words:** {int(word_total):,}\n")

    lines.append("\n## Counts by president\n")
    pres_pairs = _counts(df, "president")
    pres_pairs.sort(key=lambda kv: (-kv[1]))
    lines.append(_md_table(pres_pairs, ("president", "count")))

    lines.append("\n## Counts by source\n")
    lines.append(_md_table(_counts(df, "source"), ("source", "count")))

    lines.append("\n## Counts by event type\n")
    lines.append(_md_table(_counts(df, "event_type"), ("event_type", "count")))

    lines.append("\n## Counts by year\n")
    year_pairs = _counts(df, "year")
    year_pairs.sort(key=lambda kv: str(kv[0]))
    lines.append(_md_table(year_pairs, ("year", "count")))

    lines.append("\n## President × year matrix\n")
    if "year" in df.columns:
        pivot = (df.assign(year=df["year"].replace("", "(blank)"))
                   .pivot_table(index="president", columns="year",
                                values="id", aggfunc="count", fill_value=0))
        lines.append("```\n" + pivot.to_string() + "\n```\n")

    lines.append("\n## Quality & readability (averages)\n")
    lines.append(
        f"- mean quality_score: {_avg(df, 'quality_score')}\n"
        f"- mean word_count: {_avg(df, 'word_count')}\n"
        f"- mean Flesch reading ease: {_avg(df, 'flesch_reading_ease')}\n"
        f"- mean Flesch-Kincaid grade: {_avg(df, 'flesch_kincaid_grade')}\n"
        f"- mean type-token ratio: {_avg(df, 'type_token_ratio')}\n"
        f"- mean sentence length: {_avg(df, 'mean_sentence_length')}\n"
    )

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    LOG.info("Report written to %s", REPORT)


if __name__ == "__main__":
    build()
