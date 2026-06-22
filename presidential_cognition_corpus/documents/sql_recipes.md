# SQL recipes — exploring the corpus

Copy-paste queries for the `presidential_speech` Postgres database. Run them in:
- **pgweb** → http://localhost:8081 → **Query** tab (read-only; you can't break anything)
- **psql** → `psql -d presidential_speech`
- the **marimo dashboard** SQL cells

## Schema

```
presidents ──< speeches ──1:1── linguistic_features
                  │                    (metrics, keyed by speech_id)
                  └──< llm_extractions  (interpretive layer; empty until the LLM stage)
```
`speeches` carries `president_key`, `date`, `year`, `type` (event type), `title`,
`source`, `full_text`, and a `tsv` full-text index. Join `linguistic_features`
on `speech_id = speeches.id`.

---

## 1. Metrics with context (the everyday join)
```sql
SELECT s.date, s.type, s.title, f.mtld, f.idea_density, f.vader_compound
FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id
ORDER BY s.date
LIMIT 100;
```

## 2. Full-text search (uses the tsvector index)
```sql
SELECT date, president_key, title
FROM speeches
WHERE tsv @@ plainto_tsquery('english', 'soviet union')
ORDER BY date;
```

## 3. Compare presidents
```sql
SELECT president_key, count(*) AS n,
       round(avg(f.mtld)::numeric, 1)           AS avg_diversity,
       round(avg(f.idea_density)::numeric, 3)   AS avg_idea_density,
       round(avg(f.vader_compound)::numeric, 3) AS avg_sentiment
FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id
GROUP BY president_key
ORDER BY avg_diversity DESC;
```

## 4. Find the extremes (e.g., most "I"-heavy speeches)
```sql
SELECT s.date, s.president_key, s.title, f.first_person_singular_ratio
FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id
ORDER BY f.first_person_singular_ratio DESC
LIMIT 20;
```

## 5. One president, over time (longitudinal)
```sql
SELECT s.year,
       round(avg(f.mtld)::numeric, 1)         AS avg_diversity,
       round(avg(f.idea_density)::numeric, 3) AS avg_idea_density,
       count(*) AS n
FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id
WHERE s.president_key = 'reagan'
GROUP BY s.year
ORDER BY s.year;
```

## 6. News conferences only (the Berisha frame)
```sql
SELECT s.date, s.title, f.mtld, f.idea_density
FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id
WHERE s.title ILIKE '%news conference%'
ORDER BY s.date;
```

## 7. Coded-first in SQL (neutral identifiers, with the Trump split)
The codes live in the analysis layer (`common.neutral_code`), not the DB — but you
can reproduce them inline to present results "coded first":
```sql
WITH coded AS (
  SELECT s.*, CASE president_key
           WHEN 'reagan'  THEN 'K' WHEN 'bush41' THEN 'M'
           WHEN 'clinton' THEN 'N' WHEN 'bush43' THEN 'H'
           WHEN 'obama'   THEN 'P' WHEN 'biden'  THEN 'L'
           WHEN 'trump'   THEN CASE WHEN date >= DATE '2021-01-20' THEN 'V' ELSE 'S' END
         END AS code
  FROM speeches s
)
SELECT code, count(*) n, round(avg(f.mtld)::numeric,1) AS avg_diversity
FROM coded s JOIN linguistic_features f ON f.speech_id = s.id
GROUP BY code ORDER BY code;
```

## 8. Counts by president and event type
```sql
SELECT president_key, type, count(*) AS n
FROM speeches
GROUP BY president_key, type
ORDER BY president_key, n DESC;
```

## 9. Single-speech deep dive (text + every metric)
```sql
SELECT s.title, s.date, s.full_text, f.*
FROM speeches s JOIN linguistic_features f ON f.speech_id = s.id
WHERE s.id = '<paste a speech_id>';
```

---

## Tips
- **Export:** every result has a CSV/JSON download button in pgweb.
- **`i_to_we_ratio` is skewed:** when a speech has no "we", the ratio blows up. For
  averages, use `first_person_singular_ratio` / `first_person_plural_ratio`
  separately, or a median (`percentile_cont(0.5) WITHIN GROUP (ORDER BY ...)`).
- **The DB stores real names** (`president_key`); the neutral codes are applied in
  the Python / dashboard layer (recipe #7 reproduces them in SQL).
- For **charts** of this same data, use the marimo dashboard (:2718); pgweb is best
  for tabular browsing, ad-hoc SQL, and full-text search.
