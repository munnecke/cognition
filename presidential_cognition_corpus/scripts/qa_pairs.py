"""
qa_pairs.py — split a transcript into (reporter question, president answer) pairs.

Shared infrastructure for two downstream measures that both need the question
beside the answer:
  * coherence layer — Q->A relevance / tangentiality: did the answer engage the
    question? (cosine(question, answer))
  * affect layer — evasiveness: did the president dodge the question?

Reuses the same paragraph-level, label-driven turn parsing as
`segment_speaker.president_answers` (Q. / The President. / other-speaker labels,
topic headers, [bracket] stage directions), but instead of concatenating the
president's answers it keeps each question paired with the answer that follows it.

A "pair" = a reporter question turn (and any continuation paragraphs) immediately
followed by the president's answer turn (and its continuation), up to the next
labeled turn. Questions with no president answer (or vice versa) are dropped.
Degrades gracefully on non-Q&A transcripts (returns []).
"""

from __future__ import annotations

import re

import segment_speaker as S   # reuse the validated turn regexes / helpers

_PARA = re.compile(r"\n\s*\n")

# Newer APP transcripts run several speakers together in one paragraph, marking
# each turn with an INLINE label whose tell is a space before the period
# ("Senior Adviser Musk . ...", "Director Cohn . ..."), which ordinary sentences
# never have ("complicated."). Promote those inline labels to paragraph breaks so
# the turn parser can see them. 1-4 Title-case tokens (a name/role) + " . ".
_INLINE_LABEL = re.compile(
    r"\s+((?:[A-Z][A-Za-z.'’-]+\s+){0,3}[A-Z][A-Za-z.'’-]+)\s+\.\s+")
# A non-president speaker label at the start of a (possibly promoted) paragraph.
_OTHER_INLINE = re.compile(r"^(?:[A-Z][A-Za-z.'’-]+\s+){0,3}[A-Z][A-Za-z.'’-]+\s+\.\s")


def _promote(m: re.Match) -> str:
    label = m.group(1).strip()
    if label in ("The President", "THE PRESIDENT"):   # keep _PRES-matchable form
        return "\n\nThe President. "
    return f"\n\n{label} . "


def _promote_inline_labels(body: str) -> str:
    return _INLINE_LABEL.sub(_promote, body)


def _clean(parts: list[str]) -> str:
    text = S._BRACKET.sub(" ", " ".join(parts))
    return S._WS.sub(" ", text).strip()


def qa_pairs(body: str, min_q_words: int = 3, min_a_words: int = 3) -> list[tuple[str, str]]:
    """Return [(question, answer), ...] in document order.

    `body` is the transcript with leading '# ...' header lines already removed.
    """
    body = _promote_inline_labels(body)
    pairs: list[tuple[str, str]] = []
    cur_q: list[str] = []
    cur_a: list[str] = []
    state = None   # 'q' | 'a' | 'other' | 'pre' | None

    def flush():
        nonlocal cur_q, cur_a
        if cur_q and cur_a:
            q, a = _clean(cur_q), _clean(cur_a)
            if len(q.split()) >= min_q_words and len(a.split()) >= min_a_words:
                pairs.append((q, a))
        cur_q, cur_a = [], []

    for p in _PARA.split(body):
        p = p.strip()
        if not p:
            continue
        mq = S._QUESTION.match(p)
        if mq:
            flush()                                  # a new question closes the prior pair
            cur_q, cur_a = [p[mq.end():].strip()], []
            state = "q"
            continue
        mp = S._PRES.match(p)
        if mp:
            if cur_q:                                # answering a pending question
                cur_a.append(p[mp.end():].strip())
                state = "a"
            else:                                    # opening statement, before any question
                state = "pre"                        # ignored (no question to pair with)
            continue
        if S._OTHER_LABEL.match(p) or _OTHER_INLINE.match(p):   # another speaker -> ends answer
            flush()
            state = "other"
            continue
        if S._is_topic_header(p):
            continue
        # unlabeled continuation of the current turn
        if state == "q":
            cur_q.append(p)
        elif state == "a":
            cur_a.append(p)

    flush()
    return pairs


if __name__ == "__main__":
    import argparse, psycopg
    ap = argparse.ArgumentParser(description="Preview Q&A pairs for a speech id.")
    ap.add_argument("speech_id")
    ap.add_argument("--db", default="presidential_speech")
    args = ap.parse_args()
    with psycopg.connect(f"dbname={args.db}") as conn, conn.cursor() as cur:
        cur.execute("select full_text from speeches where id=%s", (args.speech_id,))
        body = cur.fetchone()[0]
    ps = qa_pairs(body)
    print(f"{len(ps)} Q&A pairs\n")
    for i, (q, a) in enumerate(ps[:6], 1):
        print(f"[{i}] Q: {q[:140]}")
        print(f"    A: {a[:200]}\n")
