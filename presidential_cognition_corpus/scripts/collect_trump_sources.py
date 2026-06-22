"""
collect_trump_sources.py — Trump-specific and supplemental sources (Milestone 2).

Goal: extend the corpus with Trump campaign + rally + interview + debate +
town-hall material from 2015 onward, plus official 2017-2021 and 2025-2026
remarks, beyond what the American Presidency Project carries.

Reality check on sources (read before running):

  * Trump White House Archive (2017-2021) is preserved by NARA at
    https://trumpwhitehouse.archives.gov/ — crawlable, official transcripts.
  * Biden White House (2021-2025) and the current administration site publish
    "Remarks by ..." briefing-room posts.
  * Factba.se / Roll Call Factbase: the public free-text API that powered the
    old factba.se has been repeatedly restricted and largely removed. We do NOT
    hammer it. Instead this script supports a MANUAL-INGEST path: drop saved
    .html or .txt transcripts into data_raw/factbase/ (or rev/, youtube/) and
    run with --ingest to fold them into the corpus with correct metadata.
  * Rev.com transcript library: terms restrict bulk scraping; use manual ingest.
  * YouTube captions: use the manual-ingest path with a sidecar .json holding
    {title, date, source_url, president, machine_generated:true}. Quality score
    is automatically lowered for machine captions.

So this module gives you two engines:

  (A) crawl_whitehouse_archive  — polite crawler for the NARA Trump archive and
      generic White House "remarks" briefing-room listings.
  (B) ingest_dropfolder         — fold manually-saved transcripts (factbase/rev/
      youtube/etc.) into data_raw + data_clean + metadata.

Usage
-----
    # Crawl the archived Trump White House briefing room:
    python collect_trump_sources.py --whitehouse trump_archive --max-pages 50

    # Ingest whatever you've manually dropped into data_raw/factbase etc.:
    python collect_trump_sources.py --ingest factbase rev youtube

Manual-ingest file pairing
--------------------------
For each transcript file  data_raw/<src>/<name>.(txt|html)  you MAY provide a
sidecar  data_raw/<src>/<name>.json  with any of:
    {
      "title": "...", "date": "2020-09-15", "president": "trump",
      "source_url": "https://...", "event_type": "rally",
      "machine_generated": true, "location": "Phoenix, AZ"
    }
Missing fields are inferred where possible (president from filename/text,
date from filename, etc.).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import common as C

LOG = C.get_logger("collect_trump_sources")

WHITEHOUSE_TARGETS = {
    # name -> (base listing url, source label, raw subdir key, default_president)
    # Each archive is single-administration, so the default president is reliable
    # and is used as the attribution fallback when a post (e.g. a short press
    # release or a letter) never names the president in its title/body.
    "trump_archive": (
        "https://trumpwhitehouse.archives.gov/briefings-statements/",
        "whitehouse_archive", "whitehouse_archives", "trump",
    ),
    "biden_archive": (
        "https://bidenwhitehouse.archives.gov/briefing-room/speeches-remarks/",
        "whitehouse_archive", "whitehouse_archives", "biden",
    ),
    # whitehouse.gov "current" — as of 2026 this is Trump's second term.
    "current": (
        "https://www.whitehouse.gov/news/",
        "whitehouse", "whitehouse_archives", "trump",
    ),
}

_DATE_IN_NAME = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")


# ===========================================================================
# (A) White House archive crawler
# ===========================================================================

def crawl_whitehouse(sess: C.PoliteSession, target: str, max_pages: int,
                     limit: int | None) -> int:
    if target not in WHITEHOUSE_TARGETS:
        LOG.error("Unknown whitehouse target %r. Choose from %s",
                  target, list(WHITEHOUSE_TARGETS))
        return 0
    listing, source_label, raw_key, default_pres = WHITEHOUSE_TARGETS[target]
    state = C.StateStore(f"wh_{target}")
    rows: list[dict] = []
    n = 0

    for page in range(max_pages):
        page_url = listing if page == 0 else f"{listing}page/{page + 1}/"
        html = sess.get(page_url)
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        # Briefing-room posts are article links; grab anchors inside headings.
        anchors = soup.select("article a[href], h2 a[href], h3 a[href]")
        post_links = []
        seen = set()
        for a in anchors:
            href = urljoin(page_url, a["href"].split("?")[0])
            if href.rstrip("/") == listing.rstrip("/"):
                continue
            # NB: keep the membership test grouped — without the parens, operator
            # precedence makes `not in seen` apply only to the /briefing branch,
            # letting /news and /remarks URLs through as duplicates.
            if any(k in href for k in ("/briefing", "/news", "/remarks")) and href not in seen:
                seen.add(href)
                post_links.append(href)
        if not post_links:
            LOG.info("No posts on page %d for %s; stopping.", page, target)
            break
        LOG.info("%s page %d: %d posts", target, page, len(post_links))

        for url in post_links:
            if url in state:
                continue
            if limit and n >= limit:
                break
            doc = sess.get(url)
            state.add(url)
            if not doc:
                continue
            try:
                row = _parse_and_save_wh(url, doc, source_label, raw_key, default_pres)
                if row:
                    rows.append(row)
                    n += 1
            except Exception as e:
                LOG.warning("Failed WH post %s: %s", url, e)
        state.flush()
        if limit and n >= limit:
            break

    written = C.append_metadata_rows(rows)
    state.flush()
    LOG.info("WH crawl %s DONE: %d new transcripts.", target, written)
    return written


def _parse_and_save_wh(url: str, html: str, source_label: str, raw_key: str,
                       default_pres: str = "") -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    for sel in ("h1.page-title", "h1.entry-title", "h1", "title"):
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(" ", strip=True)
            break
    date_raw = ""
    for sel in ("time", "span.posted-on", "p.meta__date", "meta[property='article:published_time']"):
        el = soup.select_one(sel)
        if el:
            date_raw = el.get("datetime") or el.get("content") or el.get_text(strip=True)
            if date_raw:
                break

    content = ""
    for sel in ("div.body-content", "div.entry-content", "article", "div.page-content"):
        el = soup.select_one(sel)
        if el:
            paras = [p.get_text(" ", strip=True) for p in el.find_all("p")
                     if p.get_text(strip=True)]
            content = "\n\n".join(paras)
            if content:
                break
    if not content:
        try:
            import trafilatura
            content = trafilatura.extract(html, favor_recall=True) or ""
        except Exception:
            content = ""
    if not content or len(content) < 200:
        return None

    # Prefer an explicit name in the post; otherwise fall back to the archive's
    # administration (these sites are single-president by construction).
    pres = C.match_president(title) or C.match_president(content[:800])
    pres_key = pres.key if pres else (default_pres or "unknown")
    pres = pres or C.PRESIDENT_BY_KEY.get(pres_key)
    iso = C.parse_date(date_raw) or ""
    doc_id = C.make_id(source_label, url, iso)
    fname = C.make_filename(iso, pres_key, source_label, title or "remarks")

    raw_path = C.SOURCE_DIRS[raw_key] / f"{doc_id}.html"
    raw_path.write_text(html, encoding="utf-8")
    clean_path = C.SPEECHES / fname
    clean_path.write_text(
        f"# {title}\n# president: {pres.display if pres else 'UNKNOWN'}\n"
        f"# date: {iso} (raw: {date_raw})\n# source: {source_label}\n"
        f"# source_url: {url}\n# retrieval_date: {C.TODAY}\n\n{content}",
        encoding="utf-8",
    )
    rec = C.Record(
        id=doc_id, president=pres_key, date=iso,
        year=(iso[:4] if iso else ""), title=title or "Remarks",
        source=source_label, source_url=url,
        word_count=str(len(content.split())), char_count=str(len(content)),
        raw_file_path=str(raw_path.relative_to(C.ROOT)),
        clean_file_path=str(clean_path.relative_to(C.ROOT)),
        quality_score="0.9", campaign_or_official="official",
        retrieval_date=C.TODAY,
    )
    return rec.to_row()


# ===========================================================================
# (B) Manual drop-folder ingest (factbase / rev / youtube / etc.)
# ===========================================================================

def ingest_dropfolder(src_keys: list[str]) -> int:
    C.ensure_dirs()
    rows: list[dict] = []
    for key in src_keys:
        folder = C.SOURCE_DIRS.get(key)
        if not folder:
            LOG.warning("Unknown source folder %r; skipping.", key)
            continue
        files = [p for p in folder.glob("*")
                 if p.suffix.lower() in (".txt", ".html", ".htm")]
        LOG.info("Ingesting %d files from %s", len(files), key)
        for fp in files:
            try:
                row = _ingest_one(fp, key)
                if row:
                    rows.append(row)
            except Exception as e:
                LOG.warning("Failed to ingest %s: %s", fp, e)
    written = C.append_metadata_rows(rows)
    LOG.info("Ingest DONE: %d new transcripts.", written)
    return written


def _ingest_one(fp: Path, src_key: str) -> dict | None:
    sidecar = fp.with_suffix(".json")
    meta = {}
    if sidecar.exists():
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            LOG.warning("Bad sidecar JSON for %s; ignoring.", fp)

    raw = fp.read_text(encoding="utf-8", errors="replace")
    if fp.suffix.lower() in (".html", ".htm"):
        try:
            import trafilatura
            content = trafilatura.extract(raw, favor_recall=True) or ""
        except Exception:
            content = BeautifulSoup(raw, "lxml").get_text("\n", strip=True)
    else:
        content = raw
    content = content.strip()
    if not content or len(content) < 100:
        LOG.warning("Thin content in %s; skipping.", fp)
        return None

    title = meta.get("title") or fp.stem.replace("_", " ").replace("-", " ")
    # date: sidecar, else from filename
    date_iso = meta.get("date") or ""
    if not date_iso:
        m = _DATE_IN_NAME.search(fp.stem)
        if m:
            date_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    date_iso = C.parse_date(date_iso) or date_iso

    pres_key = meta.get("president") or ""
    if not pres_key:
        p = C.match_president(fp.stem) or C.match_president(content[:800])
        pres_key = p.key if p else "unknown"
    pres = C.PRESIDENT_BY_KEY.get(pres_key)

    source_url = meta.get("source_url", "")
    doc_id = C.make_id(src_key, source_url or str(fp), date_iso)
    fname = C.make_filename(date_iso, pres_key, src_key, title)

    machine = bool(meta.get("machine_generated", src_key == "youtube"))
    quality = "0.5" if machine else "0.7"

    clean_path = C.SPEECHES / fname
    clean_path.write_text(
        f"# {title}\n# president: {pres.display if pres else pres_key}\n"
        f"# date: {date_iso}\n# source: {src_key}\n"
        f"# source_url: {source_url}\n# retrieval_date: {C.TODAY}\n"
        f"# machine_generated: {machine}\n\n{content}",
        encoding="utf-8",
    )
    rec = C.Record(
        id=doc_id, president=pres_key, date=date_iso,
        year=(date_iso[:4] if date_iso else ""), title=title,
        source=src_key, source_url=source_url,
        event_type=meta.get("event_type", ""),
        location=meta.get("location", ""),
        word_count=str(len(content.split())), char_count=str(len(content)),
        raw_file_path=str(fp.relative_to(C.ROOT)),
        clean_file_path=str(clean_path.relative_to(C.ROOT)),
        quality_score=quality,
        notes="machine-generated captions" if machine else "",
        retrieval_date=C.TODAY,
    )
    return rec.to_row()


def main():
    ap = argparse.ArgumentParser(description="Collect Trump-specific & supplemental sources.")
    ap.add_argument("--whitehouse", choices=list(WHITEHOUSE_TARGETS),
                    help="crawl an official/archived White House remarks listing")
    ap.add_argument("--ingest", nargs="*",
                    help="ingest manual drop-folders, e.g. --ingest factbase rev youtube")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-robots", action="store_true")
    args = ap.parse_args()

    if not args.whitehouse and not args.ingest:
        ap.error("Choose at least one of --whitehouse or --ingest.")

    if args.whitehouse:
        sess = C.PoliteSession(delay=2.0, respect_robots=not args.no_robots, logger=LOG)
        crawl_whitehouse(sess, args.whitehouse, args.max_pages, args.limit)
    if args.ingest:
        ingest_dropfolder(args.ingest)


if __name__ == "__main__":
    main()
