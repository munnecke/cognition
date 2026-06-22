"""
common.py — shared configuration, schema, logging, caching, and HTTP utilities
for the Presidential Cognition Corpus project.

Everything site-agnostic lives here so the individual collectors and the cleaning /
dedupe / metrics stages all speak the same language (paths, metadata schema,
filename convention, polite HTTP).

Nothing in here scrapes anything by itself; import it from the scripts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse, urljoin
from urllib import robotparser

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------

# Project root = parent of the scripts/ directory that holds this file.
ROOT = Path(__file__).resolve().parent.parent

DATA_RAW = ROOT / "data_raw"
DATA_CLEAN = ROOT / "data_clean"
SPEECHES = DATA_CLEAN / "speeches"
LOGS = ROOT / "logs"
CACHE = ROOT / ".cache"  # HTTP cache + scraper state (gitignored)

SOURCE_DIRS = {
    "app": DATA_RAW / "app",
    "miller_center": DATA_RAW / "miller_center",
    "whitehouse_archives": DATA_RAW / "whitehouse_archives",
    "factbase": DATA_RAW / "factbase",
    "rev": DATA_RAW / "rev",
    "youtube": DATA_RAW / "youtube",
}

METADATA_CSV = DATA_CLEAN / "metadata.csv"
METADATA_PARQUET = DATA_CLEAN / "metadata.parquet"


def ensure_dirs() -> None:
    """Create the full directory tree if it does not already exist."""
    for d in (DATA_RAW, DATA_CLEAN, SPEECHES, LOGS, CACHE, *SOURCE_DIRS.values()):
        d.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# Presidents of interest
# ----------------------------------------------------------------------------
# `key` is the short slug used in filenames and the `president` metadata column.
# `names` are matching strings used to recognise the speaker on source pages
# (case-insensitive substring match). `term_start` / `term_end` bound official
# remarks; Trump's window is deliberately extended back to the 2015 campaign.

@dataclass(frozen=True)
class President:
    key: str
    display: str
    names: tuple[str, ...]
    collect_from: str  # ISO date — earliest material we want (campaign-aware)
    collect_to: str    # ISO date — latest material we want

    @property
    def collect_from_date(self) -> date:
        return datetime.strptime(self.collect_from, "%Y-%m-%d").date()

    @property
    def collect_to_date(self) -> date:
        return datetime.strptime(self.collect_to, "%Y-%m-%d").date()


PRESIDENTS: tuple[President, ...] = (
    President("reagan", "Ronald Reagan", ("Ronald Reagan", "Reagan"), "1981-01-20", "1989-01-20"),
    President("bush41", "George H. W. Bush", ("George Bush", "George H. W. Bush"), "1989-01-20", "1993-01-20"),
    President("clinton", "Bill Clinton", ("William J. Clinton", "Bill Clinton", "Clinton"), "1993-01-20", "2001-01-20"),
    President("bush43", "George W. Bush", ("George W. Bush",), "2001-01-20", "2009-01-20"),
    President("obama", "Barack Obama", ("Barack Obama", "Obama"), "2009-01-20", "2017-01-20"),
    # Trump: campaign-era material from 2015 through the present second term.
    President("trump", "Donald Trump", ("Donald J. Trump", "Donald Trump", "Trump"), "2015-06-15", "2026-12-31"),
    President("biden", "Joseph R. Biden", ("Joseph R. Biden", "Joe Biden", "Biden"), "2021-01-20", "2025-01-20"),
)

PRESIDENT_BY_KEY = {p.key: p for p in PRESIDENTS}


def match_president(text: str) -> Optional[President]:
    """Return the President whose name appears in `text`, or None."""
    if not text:
        return None
    low = text.lower()
    for p in PRESIDENTS:
        for n in p.names:
            if n.lower() in low:
                return p
    return None


# ----------------------------------------------------------------------------
# Neutral president identifiers (Russell-inspired de-biasing device)
# ----------------------------------------------------------------------------
# Neutral symbolic labels used BY DEFAULT in comparative / affect outputs so that
# readers examine the linguistic pattern before importing political or emotional
# associations with a name. This is NOT anonymization — dates and analyses make
# identities obvious — it is a presentation-order device ("coded first, revealed
# second"), analogous to a blinded analysis. See documents/neutral_identifiers.md.
#
# Letters avoid culturally loaded ones (A/F grades, X unknown, Z sleepy, Q
# political; plus T and R for Trump / Reagan-Republican, and W/G for the Bushes)
# and are assigned arbitrarily and fixed. Trump's two non-consecutive terms are
# treated as SEPARATE presidencies (the gap may itself carry a longitudinal
# signal), split by date.

TRUMP_2ND_TERM_START = "2021-01-20"   # trump docs on/after this date -> 2nd-term id

PRESIDENT_CODE: dict[str, str] = {
    "reagan":  "K",
    "bush41":  "M",
    "clinton": "N",
    "bush43":  "H",
    "obama":   "P",
    "biden":   "L",
    # "trump" is split by term in neutral_code(): 1st-term -> S, 2nd-term -> V
}
TRUMP_CODES = ("S", "V")   # (1st term, 2nd term)

# Reverse map for the reveal / legend (code -> human label).
CODE_TO_PRESIDENT: dict[str, str] = {
    "K": "Reagan", "M": "G.H.W. Bush", "N": "Clinton", "H": "G.W. Bush",
    "P": "Obama", "L": "Biden", "S": "Trump (1st term)", "V": "Trump (2nd term)",
}


def neutral_code(president_key: str, date_iso: str = "") -> str:
    """Neutral identifier letter for a (president, date). Trump splits by term."""
    if president_key == "trump":
        return TRUMP_CODES[1] if (date_iso and date_iso >= TRUMP_2ND_TERM_START) else TRUMP_CODES[0]
    return PRESIDENT_CODE.get(president_key, "?")


def neutral_label(president_key: str, date_iso: str = "") -> str:
    """e.g. 'President K' — use in coded-first comparative / affect displays."""
    return f"President {neutral_code(president_key, date_iso)}"


# ----------------------------------------------------------------------------
# Metadata schema
# ----------------------------------------------------------------------------
# Single source of truth for column order. Collectors fill what they can; later
# stages (normalize, dedupe, classify, metrics) backfill the rest.

METADATA_FIELDS: tuple[str, ...] = (
    "id",
    "president",
    "date",
    "year",
    "title",
    "source",
    "source_url",
    "event_type",
    "location",
    "campaign_or_official",
    "prepared_or_impromptu",
    "has_q_and_a",
    "word_count",
    "char_count",
    "quality_score",
    "duplicate_cluster_id",
    "is_canonical",
    "raw_file_path",
    "clean_file_path",
    "notes",
    # --- Milestone 3 metrics (appended; safe to be empty until computed) ---
    "sentence_count",
    "mean_sentence_length",
    "median_sentence_length",
    "paragraph_count",
    "type_token_ratio",
    "flesch_reading_ease",
    "flesch_kincaid_grade",
    "speaker_label_count",
    "question_count",
    "question_answer_ratio",
    "event_duration_seconds",
    "retrieval_date",
)


@dataclass
class Record:
    """One transcript's metadata row. Unknown fields default to ''."""
    id: str = ""
    president: str = ""
    date: str = ""
    year: str = ""
    title: str = ""
    source: str = ""
    source_url: str = ""
    event_type: str = ""
    location: str = ""
    campaign_or_official: str = ""
    prepared_or_impromptu: str = ""
    has_q_and_a: str = ""
    word_count: str = ""
    char_count: str = ""
    quality_score: str = ""
    duplicate_cluster_id: str = ""
    is_canonical: str = ""
    raw_file_path: str = ""
    clean_file_path: str = ""
    notes: str = ""
    sentence_count: str = ""
    mean_sentence_length: str = ""
    median_sentence_length: str = ""
    paragraph_count: str = ""
    type_token_ratio: str = ""
    flesch_reading_ease: str = ""
    flesch_kincaid_grade: str = ""
    speaker_label_count: str = ""
    question_count: str = ""
    question_answer_ratio: str = ""
    event_duration_seconds: str = ""
    retrieval_date: str = ""

    def to_row(self) -> dict:
        return {k: ("" if v is None else v) for k, v in asdict(self).items()}


# ----------------------------------------------------------------------------
# IDs and filenames
# ----------------------------------------------------------------------------

EVENT_TYPES = (
    "formal_address", "rally", "press_conference", "interview", "debate",
    "remarks", "roundtable", "signing_statement", "radio_address",
    "town_hall", "q_and_a", "other",
)

PREP_LABELS = ("prepared", "impromptu", "mixed", "unknown")


def make_id(source: str, source_url: str, date_str: str = "") -> str:
    """Stable deterministic id from source + url (+ date). Survives re-runs."""
    h = hashlib.sha1(f"{source}|{source_url}|{date_str}".encode("utf-8")).hexdigest()
    return f"{source}_{h[:16]}"


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = _slug_re.sub("-", text.lower()).strip("-")
    return text[:max_len].strip("-") or "untitled"


def make_filename(date_str: str, president_key: str, source: str, title: str) -> str:
    """YYYY-MM-DD_president_source_short-title.txt"""
    d = date_str or "0000-00-00"
    return f"{d}_{president_key}_{source}_{slugify(title)}.txt"


# ----------------------------------------------------------------------------
# Date parsing
# ----------------------------------------------------------------------------

def parse_date(raw: str) -> Optional[str]:
    """Best-effort parse to ISO YYYY-MM-DD. Returns None on failure."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        from dateutil import parser as dparser  # local import keeps base import light
        dt = dparser.parse(raw, fuzzy=True, default=datetime(1900, 1, 1))
        if dt.year == 1900:  # parser found no year -> untrustworthy
            return None
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    ensure_dirs()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(name)s  %(message)s")

    fh = logging.FileHandler(LOGS / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


# ----------------------------------------------------------------------------
# Polite, cached, rate-limited HTTP
# ----------------------------------------------------------------------------

DEFAULT_UA = (
    "PresidentialCognitionCorpus/1.0 (academic research; "
    "contact: munnecke@gmail.com)"
)


class PoliteSession:
    """
    A requests.Session wrapper that:
      * sends a descriptive User-Agent,
      * honours robots.txt per host (can be disabled),
      * rate-limits per host,
      * caches GET responses to disk so re-runs are cheap and restartable,
      * never raises out of get() — returns None on failure and logs it.
    """

    def __init__(
        self,
        delay: float = 1.5,
        timeout: float = 30.0,
        respect_robots: bool = True,
        cache_subdir: str = "http",
        logger: Optional[logging.Logger] = None,
    ):
        import requests  # local import so `import common` works without requests
        self.requests = requests
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA})
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.log = logger or get_logger("http")
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser] = {}
        self.cache_dir = CACHE / cache_subdir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- robots --------------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        host = urlparse(url).netloc
        rp = self._robots.get(host)
        if rp is None:
            rp = robotparser.RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
            try:
                rp.set_url(robots_url)
                rp.read()
            except Exception:
                # If robots can't be read, default to allow but log it once.
                self.log.warning("Could not read robots.txt for %s; proceeding.", host)
            self._robots[host] = rp
        try:
            return rp.can_fetch(DEFAULT_UA, url)
        except Exception:
            return True

    # -- rate limit ----------------------------------------------------------
    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host, 0.0)
        wait = self.delay - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.time()

    # -- cache ---------------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.html"

    def get(self, url: str, use_cache: bool = True, force: bool = False) -> Optional[str]:
        """Return response text, or None on any failure. Caches on success."""
        cp = self._cache_path(url)
        if use_cache and not force and cp.exists():
            return cp.read_text(encoding="utf-8", errors="replace")

        if not self._allowed(url):
            self.log.warning("robots.txt disallows %s — skipping.", url)
            return None

        self._throttle(url)
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    cp.write_text(resp.text, encoding="utf-8")
                    return resp.text
                if resp.status_code in (429, 503):
                    backoff = self.delay * (2 ** attempt) + 2
                    self.log.warning("HTTP %s on %s — backing off %.1fs",
                                     resp.status_code, url, backoff)
                    time.sleep(backoff)
                    continue
                self.log.warning("HTTP %s on %s — giving up.", resp.status_code, url)
                return None
            except Exception as e:  # never abort the whole run for one URL
                self.log.warning("Request error on %s (attempt %d): %s", url, attempt + 1, e)
                time.sleep(self.delay * (attempt + 1))
        return None


# ----------------------------------------------------------------------------
# Scraper state (restartable pipeline)
# ----------------------------------------------------------------------------

class StateStore:
    """
    Tiny JSON-backed set of 'done' keys so a collector can skip work it already
    finished. One file per collector, e.g. .cache/state_app.json.
    """

    def __init__(self, name: str):
        ensure_dirs()
        self.path = CACHE / f"state_{name}.json"
        self.done: set[str] = set()
        if self.path.exists():
            try:
                self.done = set(json.loads(self.path.read_text()))
            except Exception:
                self.done = set()

    def __contains__(self, key: str) -> bool:
        return key in self.done

    def add(self, key: str) -> None:
        self.done.add(key)

    def flush(self) -> None:
        self.path.write_text(json.dumps(sorted(self.done)))


# ----------------------------------------------------------------------------
# Metadata I/O
# ----------------------------------------------------------------------------

def append_metadata_rows(rows: Iterable[dict], path: Path = METADATA_CSV) -> int:
    """
    Append rows to the metadata CSV, de-duplicating on `id` against what is
    already there. Returns the number of new rows written.
    """
    ensure_dirs()
    existing_ids: set[str] = set()
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing_ids.add(r.get("id", ""))

    new_rows = [r for r in rows if r.get("id") and r["id"] not in existing_ids]
    if not new_rows:
        return 0

    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=METADATA_FIELDS, extrasaction="ignore")
        if write_header:
            w.writeheader()
        for r in new_rows:
            full = {k: r.get(k, "") for k in METADATA_FIELDS}
            w.writerow(full)
    return len(new_rows)


def load_metadata():
    """Load metadata.csv into a pandas DataFrame (empty frame if missing)."""
    import pandas as pd
    if not METADATA_CSV.exists():
        return pd.DataFrame(columns=list(METADATA_FIELDS))
    return pd.read_csv(METADATA_CSV, dtype=str, keep_default_na=False)


def save_metadata(df) -> None:
    """Write both CSV and Parquet, preserving column order."""
    import pandas as pd
    ensure_dirs()
    for c in METADATA_FIELDS:
        if c not in df.columns:
            df[c] = ""
    df = df[list(METADATA_FIELDS)]
    df.to_csv(METADATA_CSV, index=False)
    try:
        df.to_parquet(METADATA_PARQUET, index=False)
    except Exception as e:  # pyarrow missing -> CSV still written
        get_logger("metadata").warning("Parquet write failed (%s); CSV written.", e)


TODAY = date.today().isoformat()
