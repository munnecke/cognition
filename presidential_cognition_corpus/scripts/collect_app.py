"""
collect_app.py — American Presidency Project (presidency.ucsb.edu) collector.

This is the backbone source (Milestone 1). It:

  1. Loads the advanced-search form and AUTO-DISCOVERS the taxonomy term id for
     each president from the <select name="person2"> dropdown, so we never have
     to hard-code fragile numeric ids that the site might change.
  2. Pages through advanced-search results for each president within their
     date window, collecting links to individual document pages.
  3. Downloads each document, saving the raw HTML to data_raw/app/ and writing
     a cleaned-on-arrival plain-text file plus a metadata row.

Design notes
------------
* Respects robots.txt and rate-limits (see common.PoliteSession).
* Fully restartable: a StateStore records every document already fetched, and
  the HTTP cache means re-runs cost almost nothing.
* Never aborts on a single failure — logs and continues.
* The exact CSS selectors APP uses can drift over time. We try a list of
  candidate selectors and, failing those, fall back to trafilatura. If you find
  the site has changed, adjust CANDIDATE_* below — that is the only place that
  encodes site structure.

Usage
-----
    python collect_app.py                      # all presidents
    python collect_app.py --presidents trump reagan
    python collect_app.py --limit 50           # cap docs per president (testing)
    python collect_app.py --max-pages 3        # cap result pages per president
    python collect_app.py --no-robots          # ignore robots (use responsibly)
    python collect_app.py --list-people        # just print discovered name->id
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

import common as C

LOG = C.get_logger("collect_app")
SOURCE = "app"
BASE = "https://www.presidency.ucsb.edu"
ADV_SEARCH = f"{BASE}/advanced-search"

# Candidate CSS selectors for the document page. Tried in order; first hit wins.
CANDIDATE_TITLE = [
    "div.field-ds-doc-title h1",
    "h1.title",
    "div.field-docs-title",
    "h1",
]
CANDIDATE_DATE = [
    "span.date-display-single",
    "div.field-docs-start-date span",
    "div.field-docs-person-date span.date-display-single",
]
CANDIDATE_CONTENT = [
    "div.field-docs-content",
    "div.field-ds-doc-content",
    "div.field-name-field-docs-content",
]
CANDIDATE_LOCATION = [
    "div.field-spot-state",
    "div.field-docs-state",
]
# The document page carries an explicit speaker block. Prefer this over inferring
# the president from the title/body (the body often quotes *other* presidents).
# We want just the name link, not the whole block (which includes a doc excerpt).
CANDIDATE_PERSON = [
    "div.field-docs-person h3.diet-title a",
    "div.field-docs-person .field-title a",
    "div.field-docs-person h3 a",
    "div.field-docs-person a[href*='/people/']",
]


# ---------------------------------------------------------------------------
# Person id discovery
# ---------------------------------------------------------------------------

def discover_people(sess: C.PoliteSession) -> dict[str, str]:
    """
    Return {term_id: person_name} parsed from the advanced-search person filter.
    APP renders this as <select name="person2"> with <option value="ID">Name</option>.
    """
    html = sess.get(ADV_SEARCH)
    if not html:
        LOG.error("Could not load advanced-search page to discover people.")
        return {}
    soup = BeautifulSoup(html, "lxml")
    select = soup.find("select", attrs={"name": re.compile(r"person", re.I)})
    out: dict[str, str] = {}
    if not select:
        LOG.warning("No person <select> found on advanced-search page.")
        return out
    for opt in select.find_all("option"):
        val = (opt.get("value") or "").strip()
        name = opt.get_text(strip=True)
        if val and val.isdigit():
            out[val] = name
    LOG.info("Discovered %d people in advanced-search dropdown.", len(out))
    return out


def map_presidents_to_ids(people: dict[str, str], keys: list[str]) -> dict[str, list[str]]:
    """
    Map each president key -> LIST of APP term ids. A president can have several
    entries (e.g. 'Donald J. Trump (1st Term)' and '(2nd Term)') — we collect
    all of them. Matching is done so that bush41 ('George Bush') never captures
    bush43 ('George W. Bush').
    """
    mapping: dict[str, list[str]] = {}
    for key in keys:
        pres = C.PRESIDENT_BY_KEY[key]
        ids: list[str] = []
        for tid, name in people.items():
            nl = name.lower()
            # Match if any configured name is the whole option (minus a trailing
            # parenthetical like '(1st Term)') or appears as a word-bounded substring.
            base = re.sub(r"\s*\(.*?\)\s*", "", nl).strip()
            matched = False
            for n in pres.names:
                ln = n.lower()
                if base == ln or nl == ln:
                    matched = True
                    break
                # word-bounded substring (avoids 'george bush' hitting 'george w. bush')
                if re.search(r"\b" + re.escape(ln) + r"\b", nl):
                    # extra guard: bush41 must not match if 'w.' is present
                    if key == "bush41" and "w." in nl:
                        continue
                    matched = True
                    break
            if matched and tid not in ids:
                ids.append(tid)
        if ids:
            mapping[key] = ids
            for tid in ids:
                LOG.info("president %-8s -> APP id %s (%s)", key, tid, people[tid])
        else:
            LOG.warning("Could not map president %s to an APP person id.", key)
    return mapping


# ---------------------------------------------------------------------------
# Result-page crawling
# ---------------------------------------------------------------------------

# The advanced-search form only accepts these items_per_page values; anything
# else makes Drupal drop the query and return the empty landing page.
VALID_ITEMS_PER_PAGE = {5, 10, 25, 50, 100}

# APP `category2[]` taxonomy ids for SPOKEN material only — the president
# actually speaking — for speech/tone analysis. This deliberately excludes all
# written documents (executive orders, proclamations, memoranda, messages,
# letters, signing statements, nominations, pardons, press releases, press-
# secretary statements, etc.). Passing several ids returns their UNION; the
# collector dedupes by URL, so overlap between categories is harmless.
# Edit this map to widen/narrow what counts as "speech". Verify ids against the
# live <select name="category2[]"> via the advanced-search page if APP changes.
SPOKEN_CATEGORY_IDS: dict[int, str] = {
    8:  "Spoken Addresses and Remarks",
    46: "Inaugural Addresses",
    45: "State of the Union Addresses",
    73: "News Conferences",
    74: "Interviews",
    52: "Farewell Addresses",
    53: "Fireside Chats",
    48: "Saturday/Weekly Addresses",
    55: "Eulogies",
    54: "State Dinners",
    64: "Debates",
    65: "Convention Speeches",
    49: "Presidential Nomination Acceptance Addresses",
}


def build_results_url(person_id: str, pres: C.President, page: int,
                      items: int = 100, with_dates: bool = True,
                      categories: list[int] | None = None) -> str:
    if items not in VALID_ITEMS_PER_PAGE:
        items = 100
    # list of pairs (not a dict) so we can repeat category2[] for the union.
    params: list[tuple[str, str]] = [
        ("field-keywords", ""),
        ("field-keywords2", ""),
        ("field-keywords3", ""),
        ("person2", person_id),
        ("items_per_page", str(items)),
        ("page", str(page)),
    ]
    if with_dates:
        params.append(("from[date]", pres.collect_from_date.strftime("%m-%d-%Y")))
        params.append(("to[date]", pres.collect_to_date.strftime("%m-%d-%Y")))
    for cid in (categories or []):
        params.append(("category2[]", str(cid)))
    return f"{ADV_SEARCH}?{urlencode(params)}"


# Slugs under /documents/ that are NOT transcripts (site-wide nav / category links).
NON_DOC_SLUGS = {
    "app-categories",
    "presidential-documents-archive-guidebook",
    "category-attributes",
    "",
}


# Slug patterns for auto-generated index pages that live under /documents/ but
# are NOT speech transcripts: per-president event timelines and the catch-all
# "Digest of Other White House Announcements" roundups. Excluded so they don't
# pollute the speech corpus (they recur for every president).
NON_DOC_SLUG_PATTERNS = (
    re.compile(r"-event-timeline$"),
    re.compile(r"^digest-other-white-house-announcements"),
)


def _is_real_doc(href: str) -> bool:
    if "/documents/" not in href:
        return False
    if "app-categories" in href:
        return False
    # the slug is the path segment immediately after /documents/
    try:
        slug = href.split("/documents/", 1)[1].split("/")[0].split("?")[0]
    except Exception:
        return False
    if slug in NON_DOC_SLUGS:
        return False
    if any(pat.search(slug) for pat in NON_DOC_SLUG_PATTERNS):
        return False
    return True


def extract_doc_links(html: str) -> list[str]:
    """Pull links to individual transcript documents from a results page."""
    soup = BeautifulSoup(html, "lxml")
    # Prefer links inside the results view; fall back to whole page.
    scopes = soup.select("div.view-content a[href*='/documents/']") or \
        soup.select("a[href*='/documents/']")
    seen, out = set(), []
    for a in scopes:
        href = a.get("href", "")
        if not _is_real_doc(href):
            continue
        full = urljoin(BASE, href.split("?")[0])
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


# ---------------------------------------------------------------------------
# Document parsing
# ---------------------------------------------------------------------------

def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            if txt:
                return txt
    return ""


def _content_text(soup: BeautifulSoup, html: str) -> str:
    # Preferred: the dedicated content div, paragraph by paragraph.
    for sel in CANDIDATE_CONTENT:
        el = soup.select_one(sel)
        if el:
            paras = [p.get_text(" ", strip=True) for p in el.find_all(["p", "div"])
                     if p.get_text(strip=True)]
            if paras:
                return "\n\n".join(paras)
            txt = el.get_text("\n", strip=True)
            if txt:
                return txt
    # Fallback: trafilatura main-content extraction.
    try:
        import trafilatura
        extracted = trafilatura.extract(html, include_comments=False,
                                        include_tables=False, favor_recall=True)
        if extracted:
            return extracted
    except Exception:
        pass
    return ""


def parse_document(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title = _first_text(soup, CANDIDATE_TITLE)
    date_raw = _first_text(soup, CANDIDATE_DATE)
    location = _first_text(soup, CANDIDATE_LOCATION)
    content = _content_text(soup, html)

    if not content or len(content) < 200:
        LOG.warning("Thin/empty content for %s (%d chars) — skipping.",
                    url, len(content))
        return None

    iso = C.parse_date(date_raw) or ""
    # Prefer the explicit speaker block; fall back to title, then body.
    person_name = _first_text(soup, CANDIDATE_PERSON)
    pres = (C.match_president(person_name)
            or C.match_president(title)
            or C.match_president(content[:500]))

    return {
        "title": title or "Untitled",
        "date": iso,
        "date_raw": date_raw,
        "location": location,
        "content": content,
        "president": pres,
    }


# ---------------------------------------------------------------------------
# Persisting one document
# ---------------------------------------------------------------------------

def save_document(url: str, raw_html: str, parsed: dict) -> dict | None:
    pres = parsed["president"]
    if pres is None:
        LOG.warning("No president matched for %s — keeping as 'unknown'.", url)
        pres_key = "unknown"
    else:
        pres_key = pres.key

    doc_id = C.make_id(SOURCE, url, parsed["date"])
    fname = C.make_filename(parsed["date"], pres_key, SOURCE, parsed["title"])

    raw_path = C.SOURCE_DIRS["app"] / f"{doc_id}.html"
    raw_path.write_text(raw_html, encoding="utf-8")

    clean_path = C.SPEECHES / fname
    header = (
        f"# {parsed['title']}\n"
        f"# president: {pres.display if pres else 'UNKNOWN'}\n"
        f"# date: {parsed['date']} (raw: {parsed['date_raw']})\n"
        f"# source: American Presidency Project\n"
        f"# source_url: {url}\n"
        f"# retrieval_date: {C.TODAY}\n"
        f"# location: {parsed['location']}\n"
        f"\n"
    )
    body = parsed["content"]
    clean_path.write_text(header + body, encoding="utf-8")

    wc = len(body.split())
    rec = C.Record(
        id=doc_id,
        president=pres_key,
        date=parsed["date"],
        year=(parsed["date"][:4] if parsed["date"] else ""),
        title=parsed["title"],
        source=SOURCE,
        source_url=url,
        location=parsed["location"],
        word_count=str(wc),
        char_count=str(len(body)),
        raw_file_path=str(raw_path.relative_to(C.ROOT)),
        clean_file_path=str(clean_path.relative_to(C.ROOT)),
        quality_score="0.9",  # APP is high-quality, hand-curated text
        retrieval_date=C.TODAY,
        notes="",
    )
    return rec.to_row()


# ---------------------------------------------------------------------------
# Main collection loop
# ---------------------------------------------------------------------------

def collect(presidents: list[str], limit: int | None, max_pages: int,
            respect_robots: bool, categories: list[int] | None = None) -> None:
    C.ensure_dirs()
    sess = C.PoliteSession(delay=2.0, respect_robots=respect_robots, logger=LOG)
    state = C.StateStore("app")

    # Default to spoken-only. Pass categories=[] explicitly to collect ALL types.
    if categories is None:
        categories = list(SPOKEN_CATEGORY_IDS)
    if categories:
        LOG.info("Category filter ON (%d spoken categories): %s",
                 len(categories), ", ".join(SPOKEN_CATEGORY_IDS.get(c, str(c))
                                            for c in categories))
    else:
        LOG.info("Category filter OFF — collecting ALL document types.")

    people = discover_people(sess)
    if not people:
        LOG.error("Aborting: could not discover people. Site structure may have "
                  "changed, or the network blocked the request.")
        return
    id_map = map_presidents_to_ids(people, presidents)

    total_new = 0
    for key in presidents:
        person_ids = id_map.get(key)
        if not person_ids:
            LOG.warning("Skipping %s — no APP id.", key)
            continue
        pres = C.PRESIDENT_BY_KEY[key]
        collected_for_pres = 0
        rows_buffer: list[dict] = []

        for person_id in person_ids:
            LOG.info("=== Collecting %s (APP id %s) ===", pres.display, person_id)
            empty_streak = 0
            for page in range(max_pages):
                if limit and collected_for_pres >= limit:
                    break
                results_url = build_results_url(person_id, pres, page,
                                                categories=categories)
                html = sess.get(results_url)
                if not html:
                    LOG.info("No HTTP response on page %d for %s; stopping.", page, key)
                    break
                doc_links = extract_doc_links(html)
                if not doc_links:
                    empty_streak += 1
                    LOG.info("%s id %s page %d: 0 document links (empty streak %d).",
                             key, person_id, page, empty_streak)
                    # stop early — a real result set is contiguous; 2 empties = done/broken
                    if empty_streak >= 2:
                        break
                    continue
                empty_streak = 0
                LOG.info("%s id %s page %d: %d document links",
                         key, person_id, page, len(doc_links))

                for url in doc_links:
                    if url in state:
                        continue
                    if limit and collected_for_pres >= limit:
                        break
                    doc_html = sess.get(url)
                    state.add(url)
                    if not doc_html:
                        continue
                    try:
                        parsed = parse_document(url, doc_html)
                        if not parsed:
                            continue
                        row = save_document(url, doc_html, parsed)
                        if row:
                            rows_buffer.append(row)
                            collected_for_pres += 1
                    except Exception as e:
                        LOG.warning("Failed to process %s: %s", url, e)
                        continue
                state.flush()

        written = C.append_metadata_rows(rows_buffer)
        total_new += written
        LOG.info("Wrote %d new rows for %s (collected %d).",
                 written, key, collected_for_pres)

    state.flush()
    LOG.info("DONE. %d new transcripts written to metadata.", total_new)


# ---------------------------------------------------------------------------
# Diagnostic mode — try several results-URL variants for one president and
# save them so the exact working format can be confirmed.
# ---------------------------------------------------------------------------

def diagnose(respect_robots: bool) -> None:
    C.ensure_dirs()
    sess = C.PoliteSession(delay=2.0, respect_robots=respect_robots, logger=LOG)
    people = discover_people(sess)
    id_map = map_presidents_to_ids(people, ["reagan"])
    ids = id_map.get("reagan")
    if not ids:
        LOG.error("Diagnose: could not map Reagan; cannot continue.")
        return
    pid = ids[0]
    pres = C.PRESIDENT_BY_KEY["reagan"]
    diag_dir = C.DATA_RAW / "_diag"
    diag_dir.mkdir(exist_ok=True)

    variants = {
        "A_person_dates_ipp100": build_results_url(pid, pres, 0, 100, with_dates=True),
        "B_person_only_ipp100": build_results_url(pid, pres, 0, 100, with_dates=False),
        "C_person_dates_ipp25": build_results_url(pid, pres, 0, 25, with_dates=True),
    }
    LOG.info("Diagnose: Reagan id=%s", pid)
    best_links: list[str] = []
    for name, url in variants.items():
        html = sess.get(url, force=True)
        if not html:
            LOG.info("  %-24s -> NO RESPONSE", name)
            continue
        links = extract_doc_links(html)
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else "?"
        out = diag_dir / f"{name}.html"
        out.write_text(html, encoding="utf-8")
        LOG.info("  %-24s -> %d doc links | title=%r | saved %s",
                 name, len(links), title[:60], out.name)
        if len(links) > len(best_links):
            best_links = links

    # Grab one real document page so the field parser can be verified too.
    if best_links:
        doc_url = best_links[0]
        doc_html = sess.get(doc_url, force=True)
        if doc_html:
            (diag_dir / "sample_document.html").write_text(doc_html, encoding="utf-8")
            LOG.info("Saved a sample document page: %s", doc_url)
    else:
        LOG.warning("No document links found in ANY variant — results may be served "
                    "differently than a plain GET. Send the _diag/*.html files to Claude.")
    LOG.info("Diagnose done. Saved pages under data_raw/_diag/.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Collect transcripts from the American Presidency Project.")
    ap.add_argument("--presidents", nargs="*", default=[p.key for p in C.PRESIDENTS],
                    help="president keys to collect (default: all)")
    ap.add_argument("--limit", type=int, default=None,
                    help="max docs per president (for testing)")
    ap.add_argument("--max-pages", type=int, default=200,
                    help="max result pages per president")
    ap.add_argument("--no-robots", action="store_true", help="ignore robots.txt")
    ap.add_argument("--list-people", action="store_true",
                    help="print discovered person name->id mapping and exit")
    ap.add_argument("--diagnose", action="store_true",
                    help="probe several results-URL variants for Reagan and save them")
    ap.add_argument("--all-categories", action="store_true",
                    help="collect ALL document types (default: spoken speeches/remarks only)")
    args = ap.parse_args()

    if args.list_people:
        sess = C.PoliteSession(respect_robots=not args.no_robots, logger=LOG)
        people = discover_people(sess)
        for tid, name in sorted(people.items(), key=lambda kv: kv[1]):
            print(f"{tid:>8}  {name}")
        return

    if args.diagnose:
        diagnose(respect_robots=not args.no_robots)
        return

    bad = [k for k in args.presidents if k not in C.PRESIDENT_BY_KEY]
    if bad:
        raise SystemExit(f"Unknown president keys: {bad}. "
                         f"Valid: {[p.key for p in C.PRESIDENTS]}")

    cats = [] if args.all_categories else None
    collect(args.presidents, args.limit, args.max_pages,
            respect_robots=not args.no_robots, categories=cats)


if __name__ == "__main__":
    main()
