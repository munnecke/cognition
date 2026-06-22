"""
normalize_text.py — cleaning / normalization stage.

Collectors already write a first-pass cleaned file with a comment header. This
stage enforces the project's cleaning rules uniformly across ALL sources and
(re)writes the canonical clean text, then refreshes word/char counts.

Cleaning rules (from the project spec):
  * remove navigation / menus / ads / copyright / boilerplate
  * preserve paragraph structure
  * normalize whitespace
  * preserve speaker labels (e.g. "THE PRESIDENT:", "Q:")
  * preserve applause/laughter markers, interruptions, inaudible markers
  * NEVER rewrite wording
  * keep retrieval date + source url (already in the file header)

We operate on the clean_file_path recorded in metadata. The header block
(lines beginning with '#') is preserved as-is; only the body is normalized.

Usage
-----
    python normalize_text.py            # normalize every clean file in metadata
    python normalize_text.py --limit 50
"""

from __future__ import annotations

import argparse
import re

import common as C

LOG = C.get_logger("normalize_text")

# Lines that are almost certainly boilerplate/navigation if they appear alone.
BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*(home|menu|search|skip to (main )?content)\s*$", re.I),
    re.compile(r"^\s*(share|tweet|print|email this)\s*$", re.I),
    re.compile(r"^\s*(copyright|©|\(c\))\b.*$", re.I),
    re.compile(r"^\s*all rights reserved.*$", re.I),
    re.compile(r"^\s*(privacy policy|terms of (use|service)|cookie policy)\s*$", re.I),
    re.compile(r"^\s*(advertisement|sponsored)\s*$", re.I),
    re.compile(r"^\s*(related (articles|stories|content)|read more|next|previous)\s*$", re.I),
    re.compile(r"^\s*citation:.*the american presidency project.*$", re.I),
]

# Markers we explicitly protect (never collapse/remove).
PROTECTED = re.compile(r"\[(applause|laughter|crosstalk|inaudible|cheers"
                       r"|booing|recording interrupted|the president)\b", re.I)


def normalize_body(body: str) -> str:
    # Split header (leading '#' comment lines) from body if present.
    lines = body.split("\n")

    out_lines: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            out_lines.append("")  # keep paragraph breaks
            continue
        # Drop obvious boilerplate, but never drop a line with a protected marker
        if PROTECTED.search(stripped):
            out_lines.append(re.sub(r"[ \t]+", " ", stripped))
            continue
        if any(p.match(stripped) for p in BOILERPLATE_PATTERNS):
            continue
        # collapse internal runs of whitespace, keep the line
        out_lines.append(re.sub(r"[ \t]+", " ", stripped))

    text = "\n".join(out_lines)
    # Collapse 3+ blank lines to a single blank line (paragraph break).
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Normalize unicode quotes/dashes lightly (no wording change).
    text = (text.replace("‘", "'").replace("’", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "--")
                .replace(" ", " "))
    return text.strip() + "\n"


def split_header(full: str) -> tuple[str, str]:
    """Return (header_block, body). Header = leading consecutive '#' lines."""
    lines = full.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or lines[i].strip() == ""):
        # stop the header once we hit the first non-comment, non-blank line
        if lines[i].strip() and not lines[i].startswith("#"):
            break
        i += 1
    header = "\n".join(lines[:i]).rstrip("\n")
    body = "\n".join(lines[i:])
    return header, body


def run(limit: int | None) -> None:
    df = C.load_metadata()
    if df.empty:
        LOG.warning("No metadata rows; nothing to normalize.")
        return

    updated = 0
    for idx, row in df.iterrows():
        if limit and updated >= limit:
            break
        rel = row.get("clean_file_path", "")
        if not rel:
            continue
        path = C.ROOT / rel
        if not path.exists():
            LOG.warning("Missing clean file: %s", rel)
            continue
        full = path.read_text(encoding="utf-8", errors="replace")
        header, body = split_header(full)
        clean_body = normalize_body(body)
        path.write_text((header + "\n\n" if header else "") + clean_body,
                        encoding="utf-8")

        wc = len(clean_body.split())
        df.at[idx, "word_count"] = str(wc)
        df.at[idx, "char_count"] = str(len(clean_body))
        updated += 1

    C.save_metadata(df)
    LOG.info("Normalized %d files; metadata counts refreshed.", updated)


def main():
    ap = argparse.ArgumentParser(description="Normalize/clean transcript text.")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(args.limit)


if __name__ == "__main__":
    main()
