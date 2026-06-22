"""
segment_speaker.py — extract the president's spontaneous speech from a transcript.

Cognitive-linguistic markers of decline live specifically in *unscripted* speech
(Berisha et al. 2015). A presidential news conference interleaves three things:

    The President.  [prepared opening statement — speechwriter-authored]
    <Topic Header>                                  (APP editorial annotation)
    Q. ...                                          (reporter question)
    The President.  [spontaneous answer]            <-- the signal we want
    ...

Following Berisha et al., `president_answers()` returns ONLY the president's
answers to questions: it drops the opening prepared statement, every question /
other-speaker turn, the editorial topic headers, and bracketed stage directions
like "[Laughter]". The result is the cognitively-taxing, extemporaneous portion.

This is a heuristic over APP's well-structured transcripts — paragraph-level,
label-driven. It degrades gracefully on transcripts that aren't Q&A formatted
(returns "" when no question turn is found, i.e. nothing spontaneous to keep).
"""

from __future__ import annotations

import re

# Paragraph-leading speaker labels.
_PRES = re.compile(r"^\s*(?:The President|THE PRESIDENT)\.\s*")
_QUESTION = re.compile(r"^\s*(?:Q\b[.:]?|QUESTION[.:]|REPORTER[.:]|MODERATOR[.:])", re.I)
# Any other "Name." style turn label (another speaker) — e.g. "The Vice President."
_OTHER_LABEL = re.compile(r"^\s*(?:The Vice President|The Secretary|Mr\.|Ms\.|Mrs\.|Senator|Governor|Q)\b", re.I)
_BRACKET = re.compile(r"\[[^\]]*\]")
_WS = re.compile(r"\s+")


def _is_topic_header(p: str) -> bool:
    """
    APP inserts short topic labels (e.g. 'U.S. Relations with Iran') before each
    question. Heuristic: few words and no sentence-final punctuation.
    """
    words = p.split()
    if len(words) > 9:
        return False
    return not p.rstrip().endswith((".", "!", "?", '"', ")", ":"))


def president_answers(body: str) -> str:
    """
    Return the president's spontaneous answers only (Berisha-style), as plain text.
    `body` is the transcript with the leading '# ...' header lines already removed.
    """
    paragraphs = re.split(r"\n\s*\n", body)
    state = None          # 'pres' | 'other' | None
    seen_question = False
    kept: list[str] = []

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if _QUESTION.match(p):
            state, seen_question = "other", True
            continue
        m = _PRES.match(p)
        if m:
            state = "pres"
            if seen_question:                       # skip the opening statement
                kept.append(p[m.end():])
            continue
        if _OTHER_LABEL.match(p):
            state = "other"
            continue
        if _is_topic_header(p):                      # editorial annotation
            continue
        # unlabeled paragraph → continuation of the current turn
        if state == "pres" and seen_question:
            kept.append(p)

    text = " ".join(kept)
    text = _BRACKET.sub(" ", text)                   # drop [Laughter], [name], etc.
    return _WS.sub(" ", text).strip()


def is_news_conference(title: str, clean_path: str = "") -> bool:
    """Cheap detector for APP news-conference transcripts (Berisha's source set)."""
    hay = f"{title} {clean_path}".lower()
    return "news conference" in hay or "news-conference" in hay
