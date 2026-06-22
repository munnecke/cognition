"""
run_pipeline.py — end-to-end orchestrator.

Runs the full pipeline in order, each stage tolerant of failure:

    collect (app [+ miller] [+ trump])  ->  normalize  ->  dedupe
        ->  classify  ->  metrics  ->  report

Each stage is restartable and idempotent, so you can re-run the whole thing
safely; only new/changed work is done.

Examples
--------
    # Milestone 1 only (American Presidency Project), small test slice:
    python run_pipeline.py --sources app --limit 25

    # Full Milestone 1 + Miller Center:
    python run_pipeline.py --sources app miller

    # Everything, classify with the local LM Studio model:
    python run_pipeline.py --sources app miller --llm

    # Just re-run post-processing on already-collected raw data:
    python run_pipeline.py --no-collect
"""

from __future__ import annotations

import argparse

import common as C

LOG = C.get_logger("run_pipeline")


def _safe(stage_name, fn, *a, **k):
    LOG.info("==== STAGE: %s ====", stage_name)
    try:
        fn(*a, **k)
    except Exception as e:
        LOG.exception("Stage %s failed but pipeline continues: %s", stage_name, e)


def main():
    ap = argparse.ArgumentParser(description="Run the full corpus pipeline.")
    ap.add_argument("--sources", nargs="*", default=["app"],
                    choices=["app", "miller", "trump"],
                    help="which collectors to run")
    ap.add_argument("--presidents", nargs="*", default=[p.key for p in C.PRESIDENTS])
    ap.add_argument("--limit", type=int, default=None,
                    help="cap docs per president/source (testing)")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--no-collect", action="store_true",
                    help="skip collection; only normalize/dedupe/classify/metrics/report")
    ap.add_argument("--all-categories", action="store_true",
                    help="APP: collect ALL document types (default: spoken speeches/remarks only)")
    ap.add_argument("--llm", action="store_true",
                    help="use local LM Studio model for classification")
    ap.add_argument("--features", action="store_true",
                    help="run the spaCy NLP feature extractor (writes linguistic_features.csv)")
    ap.add_argument("--no-robots", action="store_true")
    args = ap.parse_args()

    C.ensure_dirs()

    if not args.no_collect:
        if "app" in args.sources:
            import collect_app
            _safe("collect_app", collect_app.collect,
                  args.presidents, args.limit, args.max_pages,
                  respect_robots=not args.no_robots,
                  categories=([] if args.all_categories else None))
        if "miller" in args.sources:
            import collect_miller
            _safe("collect_miller", collect_miller.collect,
                  args.limit, args.max_pages, respect_robots=not args.no_robots)
        if "trump" in args.sources:
            import collect_trump_sources as cts
            sess = C.PoliteSession(delay=2.0, respect_robots=not args.no_robots, logger=LOG)
            _safe("collect_trump:whitehouse", cts.crawl_whitehouse,
                  sess, "trump_archive", args.max_pages, args.limit)
            _safe("collect_trump:ingest", cts.ingest_dropfolder,
                  ["factbase", "rev", "youtube"])

    import normalize_text
    _safe("normalize_text", normalize_text.run, None)

    import dedupe
    _safe("dedupe", dedupe.run, 90, 0.85)

    import classify_event_type
    _safe("classify_event_type", classify_event_type.run, args.llm, False, None)

    import compute_metrics
    import os as _os
    _safe("compute_metrics", compute_metrics.run, False, None,
          max(1, (_os.cpu_count() or 4) - 2))   # parallel sentence-splitting

    if args.features:
        import extract_features
        _safe("extract_features", extract_features.run, True, None, "en_core_web_sm")

    import build_report
    _safe("build_report", build_report.build)

    LOG.info("PIPELINE COMPLETE. See data_clean/metadata.csv and logs/collection_report.md")


if __name__ == "__main__":
    main()
