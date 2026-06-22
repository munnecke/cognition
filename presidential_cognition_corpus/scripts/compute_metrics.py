"""
compute_metrics.py — Milestone 3 corpus metrics.

For every transcript, compute and store in metadata:
    word_count, sentence_count, mean_sentence_length, median_sentence_length,
    paragraph_count, type_token_ratio, flesch_reading_ease,
    flesch_kincaid_grade, speaker_label_count, question_count,
    question_answer_ratio, (event_duration_seconds left blank unless known)

Uses textstat for readability and a light spaCy/regex sentence splitter. spaCy
is optional: if the model isn't installed we fall back to a regex splitter so
the stage never hard-fails.

These are descriptive corpus metrics only — NOT cognition analysis. They set up
later work (semantic drift, lexical diversity over time, prepared-vs-impromptu
comparisons, within-president aging, cross-president comparisons).

Usage
-----
    python compute_metrics.py
    python compute_metrics.py --only-missing --limit 200
"""

from __future__ import annotations

import argparse
import re
import statistics

import common as C

LOG = C.get_logger("compute_metrics")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_Q_LABEL = re.compile(r"^\s*(Q[:.\s]|QUESTION[:.]|REPORTER[:.]|MODERATOR[:.])", re.I | re.M)
_A_LABEL = re.compile(r"^\s*(THE PRESIDENT|THE VICE PRESIDENT|PRESIDENT [A-Z]+)[:.]", re.M)
_SPEAKER = re.compile(r"^\s*[A-Z][A-Z .'\-]{2,40}:", re.M)
_WORD = re.compile(r"[A-Za-z']+")

_nlp = None
_textstat_ready = None


def _ensure_textstat_data() -> bool:
    """
    textstat needs the NLTK 'cmudict' corpus for syllable-based readability
    scores. It auto-downloads on first use if the network is available. We try
    once and cache the result; on failure, readability columns stay blank but
    the rest of the metrics still compute.
    """
    global _textstat_ready
    if _textstat_ready is not None:
        return _textstat_ready
    try:
        import nltk
        try:
            nltk.data.find("corpora/cmudict")
        except LookupError:
            nltk.download("cmudict", quiet=True)
            nltk.data.find("corpora/cmudict")
        _textstat_ready = True
    except Exception as e:
        LOG.warning("textstat readability data unavailable (%s); "
                    "Flesch scores will be blank. Run "
                    "`python -m nltk.downloader cmudict` once with network.", e)
        _textstat_ready = False
    return _textstat_ready


def _get_nlp():
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        try:
            _nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer", "tagger"])
        except Exception:
            _nlp = spacy.blank("en")
            _nlp.add_pipe("sentencizer")
    except Exception:
        _nlp = False  # sentinel: spaCy unavailable
    return _nlp


def split_sentences(text: str) -> list[str]:
    nlp = _get_nlp()
    if nlp:
        try:
            doc = nlp(text[:1_000_000])  # spaCy length guard
            return [s.text.strip() for s in doc.sents if s.text.strip()]
        except Exception:
            pass
    # regex fallback
    parts = _SENT_SPLIT.split(re.sub(r"\s+", " ", text))
    return [p.strip() for p in parts if p.strip()]


def _read_body(rel: str) -> str:
    path = C.ROOT / rel
    if not path.exists():
        return ""
    return "\n".join(l for l in path.read_text(encoding="utf-8", errors="replace").split("\n")
                     if not l.startswith("#")).strip()


def compute(body: str, sentences: list[str] | None = None) -> dict:
    words = _WORD.findall(body)
    wc = len(words)
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    if sentences is None:
        sentences = split_sentences(body)
    sent_lens = [len(_WORD.findall(s)) for s in sentences if _WORD.findall(s)]

    ttr = (len({w.lower() for w in words}) / wc) if wc else 0.0
    q_count = len(_Q_LABEL.findall(body))
    a_count = len(_A_LABEL.findall(body))
    qa_ratio = (q_count / a_count) if a_count else (float(q_count) if q_count else 0.0)
    speaker_labels = len(_SPEAKER.findall(body))

    # readability via textstat (guarded)
    fre = fkg = ""
    if wc >= 20 and _ensure_textstat_data():
        try:
            import textstat
            fre = round(textstat.flesch_reading_ease(body), 2)
            fkg = round(textstat.flesch_kincaid_grade(body), 2)
        except Exception as e:
            LOG.debug("textstat failed on a doc: %s", e)

    return {
        "word_count": str(wc),
        "char_count": str(len(body)),
        "sentence_count": str(len(sentences)),
        "mean_sentence_length": str(round(statistics.mean(sent_lens), 2)) if sent_lens else "0",
        "median_sentence_length": str(round(statistics.median(sent_lens), 2)) if sent_lens else "0",
        "paragraph_count": str(len(paragraphs)),
        "type_token_ratio": str(round(ttr, 4)),
        "flesch_reading_ease": str(fre),
        "flesch_kincaid_grade": str(fkg),
        "speaker_label_count": str(speaker_labels),
        "question_count": str(q_count),
        "question_answer_ratio": str(round(qa_ratio, 3)),
    }


def run(only_missing: bool, limit: int | None, n_process: int = 1) -> None:
    df = C.load_metadata()
    if df.empty:
        LOG.warning("No metadata; nothing to measure.")
        return

    todo = []  # (idx, body)
    for idx, row in df.iterrows():
        if limit and len(todo) >= limit:
            break
        if only_missing and (row.get("sentence_count") or "").strip():
            continue
        body = _read_body(row.get("clean_file_path", ""))
        if body:
            todo.append((idx, body))
    if not todo:
        LOG.info("Nothing to compute.")
        return

    nlp = _get_nlp()
    LOG.info("Computing metrics for %d transcripts (n_process=%d).", len(todo), n_process)
    n = 0
    if nlp:
        # parallelize the spaCy sentence-splitting; compute the rest per doc.
        pairs = [(b[:1_000_000], (idx, b)) for idx, b in todo]
        for doc, (idx, body) in nlp.pipe(pairs, as_tuples=True, batch_size=64, n_process=n_process):
            sents = [s.text.strip() for s in doc.sents if s.text.strip()]
            for k, v in compute(body, sents).items():
                df.at[idx, k] = v
            n += 1
            if n % 1000 == 0:
                C.save_metadata(df)          # periodic save -> crash-safe + resumable
                LOG.info("...%d processed (saved)", n)
    else:                                    # regex-only fallback
        for idx, body in todo:
            for k, v in compute(body).items():
                df.at[idx, k] = v
            n += 1
    C.save_metadata(df)
    LOG.info("Computed metrics for %d transcripts.", n)


def main():
    ap = argparse.ArgumentParser(description="Compute corpus metrics (Milestone 3).")
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--n-process", type=int, default=1,
                    help="spaCy worker processes for sentence splitting (parallel)")
    args = ap.parse_args()
    run(args.only_missing, args.limit, args.n_process)


if __name__ == "__main__":
    main()
