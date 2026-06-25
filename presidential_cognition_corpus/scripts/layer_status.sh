#!/usr/bin/env bash
# layer_status.sh — one-glance coverage of every analysis layer.
#
# Shows, for the analyzable corpus (canonical, presidential_voice, >=200 words),
# how far each layer has been computed: the deterministic spontaneity selector,
# the embedding-based coherence layer, and the LLM affect layer. Run it any time
# to track in-progress batch jobs.
#
# Usage:  scripts/layer_status.sh
set -u
DB="${PG_DB:-presidential_speech}"

psql "$DB" -q <<'SQL'
\pset border 2
\echo '== analyzable corpus (is_canonical AND presidential_voice AND word_count>=200) =='
SELECT count(*) AS analyzable_docs
FROM speeches WHERE is_canonical AND presidential_voice AND word_count>=200;

\echo ''
\echo '== spontaneity (llm_extractions, prompt_version=spontaneity-v2) =='
SELECT
  count(*) FILTER (WHERE e.id IS NOT NULL)                         AS scored,
  count(*)                                                         AS target,
  round(100.0*count(*) FILTER (WHERE e.id IS NOT NULL)/count(*),1) AS pct,
  count(*) FILTER (WHERE e.confidence_score>=0.5)                  AS impromptu_ge_0_5,
  count(*) FILTER (WHERE e.confidence_score>=0.7)                  AS impromptu_ge_0_7
FROM speeches s
LEFT JOIN llm_extractions e
  ON e.speech_id=s.id AND e.extraction_type='spontaneity' AND e.prompt_version='spontaneity-v2'
WHERE s.is_canonical AND s.presidential_voice AND s.word_count>=200;

\echo ''
\echo '== coherence (speech_coherence) — denominator = impromptu set (spontaneity>=0.5) =='
SELECT
  count(*) FILTER (WHERE c.speech_id IS NOT NULL)                          AS computed,
  count(*)                                                                 AS impromptu_target,
  round(100.0*count(*) FILTER (WHERE c.speech_id IS NOT NULL)
        /NULLIF(count(*),0),1)                                             AS pct
FROM speeches s
JOIN llm_extractions e
  ON e.speech_id=s.id AND e.extraction_type='spontaneity'
 AND e.prompt_version='spontaneity-v2' AND e.confidence_score>=0.5
LEFT JOIN speech_coherence c ON c.speech_id=s.id
WHERE s.is_canonical AND s.presidential_voice AND s.word_count>=200;

\echo ''
\echo '== affect (llm_extractions affect dimensions) — coverage of impromptu set (spontaneity>=0.5) =='
SELECT
  a.extraction_type                                                       AS dimension,
  count(DISTINCT a.speech_id)                                             AS scored
FROM llm_extractions a
WHERE a.extraction_type IN ('anger','empathy','evasiveness','emotional_intensity')
GROUP BY a.extraction_type
ORDER BY 1;
SQL

# Tail any live run logs if present.
LOGDIR="$(dirname "$0")/../logs"
for f in spontaneity_overnight.log affect_overnight.log coherence.log; do
  [ -f "$LOGDIR/$f" ] && printf "\n-- tail %s --\n" "$f" && tail -2 "$LOGDIR/$f"
done
true
