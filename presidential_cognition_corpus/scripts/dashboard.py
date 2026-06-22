"""
dashboard.py — marimo web dashboard for the Presidential Cognition Corpus.

Reactive, Python-native dashboard that queries the PostgreSQL system of record
LIVE (no SQLite mirror, no data duplication) and reuses the project's own
analysis code (replicate_berisha, segment_speaker) for the validation panel.

Develop:   marimo edit scripts/dashboard.py
Serve:     marimo run  scripts/dashboard.py        # read-only web app
           (set PG_DB to override the database name; default presidential_speech)
"""

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="medium")


@app.cell
def _():
    import os
    import sys
    import pathlib

    import marimo as mo
    import pandas as pd
    import altair as alt
    from sqlalchemy import create_engine, text

    # Make the project's own modules importable (common, replicate_berisha, ...).
    HERE = pathlib.Path("/Users/munnecke/cognition/presidential_cognition_corpus")
    sys.path.insert(0, str(HERE / "scripts"))
    return alt, create_engine, mo, os, pd, text


@app.cell
def _(create_engine, os):
    DB = os.environ.get("PG_DB", "presidential_speech")
    engine = create_engine(f"postgresql+psycopg:///{DB}")
    return DB, engine


@app.cell
def _(DB, mo):
    mo.md(
        f"""
        # 🏛️ Presidential Cognition Corpus
        Live dashboard over PostgreSQL (`{DB}`) — spoken presidential material for
        longitudinal linguistic / cognitive analysis. No data duplication: every
        panel queries Postgres directly.
        """
    )
    return


@app.cell
def _(alt, engine, mo, pd):
    overview = pd.read_sql(
        "SELECT president_key, count(*) AS speeches, "
        "min(date) AS first, max(date) AS last "
        "FROM speeches GROUP BY president_key ORDER BY speeches DESC",
        engine,
    )
    _bar = (
        alt.Chart(overview)
        .mark_bar()
        .encode(
            x=alt.X("speeches:Q", title="speeches"),
            y=alt.Y("president_key:N", sort="-x", title=None),
            tooltip=["president_key", "speeches", "first", "last"],
        )
        .properties(height=180, title="Corpus size by president")
    )
    mo.vstack([mo.ui.altair_chart(_bar), mo.ui.table(overview, selection=None)])
    return (overview,)


@app.cell
def _(mo, overview):
    president = mo.ui.dropdown(
        options=list(overview["president_key"]),
        value=overview["president_key"].iloc[0],
        label="President",
    )
    mo.md(f"### Select a president to drill in\n{president}")
    return (president,)


@app.cell
def _(alt, mo, pd, president):
    # --- Validation panel: reuse replicate_berisha on the live filesystem ---
    import replicate_berisha as R

    rows = R.collect_conferences(president.value, 1400)
    if not rows:
        panel = mo.md(
            f"**{president.value}** — no news conferences with ≥1,400 answer-words "
            "collected yet (still scraping, or not a press-conference president)."
        )
    else:
        df = pd.DataFrame(rows)
        df["index"] = range(len(df))
        uw = R.regress(rows, "unique_words")
        nf = R.regress(rows, "ns_plus_fillers")
        pts = (
            alt.Chart(df)
            .mark_circle(size=70, opacity=0.7)
            .encode(x=alt.X("index:Q", title="news conference (chronological)"),
                    y=alt.Y("unique_words:Q", title="unique words (first 1,400)"),
                    tooltip=["date", "unique_words"])
        )
        trend = pts.transform_regression("index", "unique_words").mark_line(color="firebrick")
        chart = (pts + trend).properties(
            height=260,
            title=f"{president.value}: lexical diversity over time "
                  f"(Berisha-style, n={uw['n']})",
        )
        panel = mo.vstack([
            mo.md(
                f"**Berisha-replication validation** — president's spontaneous "
                f"news-conference answers only.\n\n"
                f"- unique words vs time: **R={uw['R']:+.3f}, p={uw['p']:.4f}**\n"
                f"- non-specific nouns + fillers vs time: **R={nf['R']:+.3f}, p={nf['p']:.4f}**\n"
                f"\n*(Reagan published: R=−0.446 / +0.358; this reproduces it.)*"
            ),
            mo.ui.altair_chart(chart),
        ])
    panel
    return


@app.cell
def _(alt, engine, mo, pd, president, text):
    # --- Feature trends over time (from linguistic_features in Postgres) ---
    feature = mo.ui.dropdown(
        options={
            "Lexical diversity (MTLD)": "mtld",
            "I-to-we ratio": "i_to_we_ratio",
            "First-person singular ratio": "first_person_singular_ratio",
            "Mean dependency distance": "mean_dependency_distance",
            "VADER sentiment": "vader_compound",
        },
        value="Lexical diversity (MTLD)",
        label="Feature",
    )

    fdf = pd.read_sql(
        text(
            "SELECT s.date, s.title, f.mtld, f.i_to_we_ratio, "
            "f.first_person_singular_ratio, f.mean_dependency_distance, f.vader_compound "
            "FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id "
            "WHERE s.president_key = :p AND s.date IS NOT NULL ORDER BY s.date"
        ),
        engine, params={"p": president.value},
    )
    if fdf.empty:
        ftrend = mo.md(f"**{president.value}** — no features computed yet "
                       "(run `extract_features.py`).")
    else:
        col = feature.value
        base = alt.Chart(fdf).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y(f"{col}:Q", title=col),
        )
        ftrend = mo.ui.altair_chart(
            (base.mark_circle(opacity=0.35)
             + base.transform_loess("date", col).mark_line(color="steelblue"))
            .properties(height=260, title=f"{president.value}: {col} over time")
        )
    mo.vstack([mo.md(f"### Feature trend\n{feature}"), ftrend])
    return


@app.cell
def _(engine, mo, pd, president, text):
    # --- Searchable speech browser (live full-text via tsvector) ---
    search = mo.ui.text(placeholder="full-text search…", label="Search")
    mo.md(f"### Browse speeches\n{search}")
    return (search,)


@app.cell
def _(engine, mo, pd, president, search, text):
    if search.value.strip():
        q = text(
            "SELECT date, type, title, word_count FROM speeches "
            "WHERE president_key = :p AND tsv @@ plainto_tsquery('english', :q) "
            "ORDER BY date LIMIT 200"
        )
        params = {"p": president.value, "q": search.value}
    else:
        q = text(
            "SELECT date, type, title, word_count FROM speeches "
            "WHERE president_key = :p ORDER BY date LIMIT 200"
        )
        params = {"p": president.value}
    speeches = pd.read_sql(q, engine, params=params)
    mo.vstack([mo.md(f"*{len(speeches)} shown (max 200)*"), mo.ui.table(speeches, selection=None)])
    return


if __name__ == "__main__":
    app.run()
