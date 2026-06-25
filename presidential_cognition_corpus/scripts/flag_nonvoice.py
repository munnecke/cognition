"""
flag_nonvoice.py — mark transcripts that are NOT in the president's spoken voice.

The APP and Miller sources were filtered to *spoken* categories at collection,
but the Trump/NARA `whitehouse_archive` ingest was never category-filtered, so it
leaked White House comms-office output written in the third person — disaster-
declaration approvals, award announcements, First/Second-Lady press releases,
Readouts, Joint Statements, Messages to Congress. These were never SPOKEN by the
president; including them skews any corpus-wide analysis (vocabulary, sentiment,
the "remarks" baseline) and wastes LLM scoring time.

This sets a durable derived flag `speeches.presidential_voice` (default TRUE;
FALSE for the non-voice docs). All downstream queries/analyses should filter
`presidential_voice` (the spontaneity scorer does). Idempotent + re-runnable as
the corpus grows. The flat files remain the source of truth; this is a derived
column, so re-run after any reload.

Matching is **title-anchored and conservative** (validated by sampling, ~270
docs, ~1.2% of corpus). It targets titles that ARE the written instrument /
press release (prefix match), and crucially KEEPS the president's real speeches:
"President Donald J. Trump Delivers Remarks on X" is retained (that's how NARA
titles his actual remarks); only "President Trump Approves/to Award ..." is cut.

Usage:  python flag_nonvoice.py [--db presidential_speech] [--dry-run]
"""

from __future__ import annotations

import argparse
import os

import psycopg

import common as C

LOG = C.get_logger("flag_nonvoice")

# Title-anchored non-voice predicate. Two arms:
#  (1) the title STARTS WITH a written-instrument / comms label, or
#  (2) it's a third-person "<Official> <Name> ..." headline that is NOT one of
#      the spoken forms (Remarks/Address/Interview/...). The negative guard is
#      what preserves "President ... Delivers Remarks ..." (real speech).
NONVOICE_SQL = r"""
 (
    title ~* '^(Joint Statement|Statement by the Press Secretary|Statement by the Vice President|Readout|Fact Sheet|Background Press|Press Briefing by|Press Gaggle|Nomination of|Appointment of|Designation of|Memorandum (of|on|for)|Message to the (Congress|Senate|House)|Executive Order|Proclamation|Notice on|Letter to)'
  OR (title ~* '^(President|Vice President|First Lady|Second Lady|Acting Secretary|Secretary) [A-Z]'
      AND title !~* '\y(Remarks|Address|Interview|Q&A|Question|News Conf|Press Conf|Exchange|Statement on Signing|Speech|Toast|Eulogy|Debate|Town Hall|Roundtable)\y')
 )
 -- ...but KEEP anything explicitly spoken "by [the] President/Vice President"
 -- (e.g. "Press Briefing by President Biden, ..." — he speaks in it; the
 -- segmenter pulls his turns). Only staff-only briefings stay excluded.
 -- NB: Postgres regex word boundary is \y, NOT \b (\b is a backspace here).
 AND title !~* 'by (the )?(President|Vice President)\y'
"""


def target_dsn(db: str) -> str:
    if "PG_DSN" in os.environ:
        parts = [p for p in os.environ["PG_DSN"].split() if not p.startswith("dbname=")]
        return " ".join(parts + [f"dbname={db}"])
    return f"dbname={db}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="presidential_speech")
    ap.add_argument("--dry-run", action="store_true",
                    help="report counts + a sample, but do not write")
    args = ap.parse_args()

    with psycopg.connect(target_dsn(args.db), autocommit=True) as conn, conn.cursor() as cur:
        # Idempotent: add the column (default TRUE) if it isn't there yet.
        cur.execute("ALTER TABLE speeches ADD COLUMN IF NOT EXISTS "
                    "presidential_voice boolean NOT NULL DEFAULT true")

        cur.execute(f"SELECT count(*) FROM speeches WHERE {NONVOICE_SQL}")
        n_match = cur.fetchone()[0]
        LOG.info("title-anchored non-voice matches: %d", n_match)

        cur.execute(f"SELECT title FROM speeches WHERE {NONVOICE_SQL} "
                    "ORDER BY md5(id) LIMIT 8")
        for (t,) in cur.fetchall():
            LOG.info("  flag: %s", (t or "")[:90])

        if args.dry_run:
            LOG.info("dry-run — no changes written")
            return

        # Reset then re-apply, so the flag is fully determined by the predicate
        # (re-runs stay correct even if the predicate is later tightened).
        cur.execute("UPDATE speeches SET presidential_voice = true "
                    "WHERE presidential_voice = false")
        cur.execute(f"UPDATE speeches SET presidential_voice = false WHERE {NONVOICE_SQL}")
        cur.execute("SELECT count(*) FROM speeches WHERE NOT presidential_voice")
        LOG.info("marked %d speeches presidential_voice = FALSE", cur.fetchone()[0])


if __name__ == "__main__":
    main()
