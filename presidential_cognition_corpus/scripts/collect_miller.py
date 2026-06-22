"""
collect_miller.py — Miller Center presidential speeches collector.

Miller Center (millercenter.org) hosts a smaller but very clean, curated set of
presidential speeches with high-quality transcripts. Listing pages are at:

    https://millercenter.org/the-presidency/presidential-speeches

Individual speeches live at:

    https://millercenter.org/the-presidency/presidential-speeches/<slug>

The listing is a Drupal "view" that paginates with ?page=N. We crawl those
pages for speech links, then download and parse each speech page. Transcript
text is in a ".transcript" / ".view-transcript" block; we fall back to
trafilatura if the markup has changed.

Same operational guarantees as collect_app.py: robots-aware, rate-limited,
cached, restartable, failure-tolerant.

Usage
-----
    python collect_miller.py
    python collect_miller.py --limit 50
    python collect_miller.py --max-pages 5
"""

from __future__ import annotations

import argparse
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import common as C

LOG = C.get_logger("collect_miller")
SOURCE = "miller_center"
BASE = "https://millercenter.org"
LISTING = f"{BASE}/the-presidency/presidential-speeches"

CANDIDATE_CONTENT = [
    "div.transcript-inner",
    "div.view-transcript",
    "div.transcript",
    "div.field--name-field-transcript",
]
CANDIDATE_TITLE = ["h2.presidential-speeches--title", "h1.presidential-speeches--title",
                   "h1.title", "h1"]
CANDIDATE_DATE = ["p.episode-date", "span.date-display-single", "time"]
# Explicit speaker block in the "About this speech" sidebar. Prefer this over
# inferring from title/body: inaugurals and eulogies routinely name *other*
# presidents in the transcript (e.g. predecessors seated on the dais).
CANDIDATE_PERSON = ["p.president-name", ".about-this-episode--inner .president-name"]


def crawl_listing(sess: C.PoliteSession, max_pages: int) -> list[str]:
    links: list[str] = []
    seen = set()
    for page in range(max_pages):
        url = f"{LISTING}?page={page}"
        html = sess.get(url)
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        page_links = [
            urljoin(BASE, a["href"].split("?")[0])
            for a in soup.select("a[href*='/presidential-speeches/']")
            if a.get("href") and a["href"].rstrip("/").split("/")[-1]
            not in ("presidential-speeches",)
        ]
        new = []
        for l in page_links:
            if l != LISTING and l not in seen:
                seen.add(l)
                new.append(l)
        if not new:
            LOG.info("No new links on page %d; stopping listing crawl.", page)
            break
        links.extend(new)
        LOG.info("Listing page %d: %d new speech links (total %d)",
                 page, len(new), len(links))
    return links


def _first_text(soup, selectors):
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(" ", strip=True)
    return ""


def parse_speech(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title = _first_text(soup, CANDIDATE_TITLE)
    date_raw = _first_text(soup, CANDIDATE_DATE)

    content = ""
    for sel in CANDIDATE_CONTENT:
        el = soup.select_one(sel)
        if el:
            paras = [p.get_text(" ", strip=True) for p in el.find_all("p")
                     if p.get_text(strip=True)]
            content = "\n\n".join(paras) if paras else el.get_text("\n", strip=True)
            if content:
                break
    if not content:
        try:
            import trafilatura
            content = trafilatura.extract(html, favor_recall=True) or ""
        except Exception:
            content = ""

    if not content or len(content) < 200:
        LOG.warning("Thin content for %s — skipping.", url)
        return None

    # Prefer the explicit speaker block; fall back to title, then body.
    person_name = _first_text(soup, CANDIDATE_PERSON)
    pres = (C.match_president(person_name)
            or C.match_president(title)
            or C.match_president(content[:500]))
    return {
        "title": title or "Untitled",
        "date": C.parse_date(date_raw) or "",
        "date_raw": date_raw,
        "content": content,
        "president": pres,
    }


def save_speech(url: str, raw_html: str, parsed: dict) -> dict | None:
    pres = parsed["president"]
    pres_key = pres.key if pres else "unknown"
    doc_id = C.make_id(SOURCE, url, parsed["date"])
    fname = C.make_filename(parsed["date"], pres_key, SOURCE, parsed["title"])

    raw_path = C.SOURCE_DIRS["miller_center"] / f"{doc_id}.html"
    raw_path.write_text(raw_html, encoding="utf-8")

    header = (
        f"# {parsed['title']}\n"
        f"# president: {pres.display if pres else 'UNKNOWN'}\n"
        f"# date: {parsed['date']} (raw: {parsed['date_raw']})\n"
        f"# source: Miller Center\n"
        f"# source_url: {url}\n"
        f"# retrieval_date: {C.TODAY}\n\n"
    )
    clean_path = C.SPEECHES / fname
    clean_path.write_text(header + parsed["content"], encoding="utf-8")

    body = parsed["content"]
    rec = C.Record(
        id=doc_id, president=pres_key, date=parsed["date"],
        year=(parsed["date"][:4] if parsed["date"] else ""),
        title=parsed["title"], source=SOURCE, source_url=url,
        word_count=str(len(body.split())), char_count=str(len(body)),
        raw_file_path=str(raw_path.relative_to(C.ROOT)),
        clean_file_path=str(clean_path.relative_to(C.ROOT)),
        quality_score="0.95", retrieval_date=C.TODAY,
    )
    return rec.to_row()


def collect(limit: int | None, max_pages: int, respect_robots: bool) -> None:
    C.ensure_dirs()
    sess = C.PoliteSession(delay=2.0, respect_robots=respect_robots, logger=LOG)
    state = C.StateStore("miller")

    links = crawl_listing(sess, max_pages)
    LOG.info("Found %d candidate speech links.", len(links))

    rows: list[dict] = []
    n = 0
    for url in links:
        if url in state:
            continue
        if limit and n >= limit:
            break
        html = sess.get(url)
        state.add(url)
        if not html:
            continue
        try:
            parsed = parse_speech(url, html)
            if not parsed:
                continue
            # Only keep presidents in scope.
            if parsed["president"] is None:
                LOG.info("Skipping out-of-scope speaker: %s", url)
                continue
            row = save_speech(url, html, parsed)
            if row:
                rows.append(row)
                n += 1
        except Exception as e:
            LOG.warning("Failed on %s: %s", url, e)
        state.flush()

    written = C.append_metadata_rows(rows)
    state.flush()
    LOG.info("DONE. %d new Miller Center transcripts written.", written)


def main():
    ap = argparse.ArgumentParser(description="Collect Miller Center presidential speeches.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--no-robots", action="store_true")
    args = ap.parse_args()
    collect(args.limit, args.max_pages, respect_robots=not args.no_robots)


if __name__ == "__main__":
    main()
