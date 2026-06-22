"""
extract_features.py — deterministic NLP feature extraction (cognition layer).

Where compute_metrics.py produces light *descriptive* corpus metrics into
metadata.csv, this module produces the richer, reproducible linguistic-feature
set used for longitudinal speech/tone/cognition analysis. It writes a SEPARATE
table — data_clean/linguistic_features.csv (+ .parquet) — keyed by speech `id`,
so:

  * the canonical metadata schema (common.METADATA_FIELDS) stays lean, and
  * the (ever-growing) feature set maps 1:1 to a future Postgres
    `linguistic_features` table without schema churn.

Everything here is DETERMINISTIC and 100% local — no LLM. That is the point:
these features are the longitudinal backbone, so a trend over time must never
move because a model version changed. Interpretive/pragmatic signals (evasion,
rhetorical strategy, nuanced affect) belong in the separate LLM-extraction layer.

Backbone: spaCy (POS, morphology, dependency parse, lemmas) + length-robust
lexical diversity (MTLD, MATTR) + VADER rule-based sentiment. spaCy is required
for the full feature set; if its model is missing we log and fill blanks rather
than hard-failing, and never abort the run on one bad transcript.

Usage
-----
    python extract_features.py
    python extract_features.py --only-missing --limit 200
    python extract_features.py --model en_core_web_sm
"""

from __future__ import annotations

import argparse
import re
from collections import Counter

import common as C

LOG = C.get_logger("extract_features")

FEATURES_CSV = C.DATA_CLEAN / "linguistic_features.csv"
FEATURES_PARQUET = C.DATA_CLEAN / "linguistic_features.parquet"

EXTRACTOR_VERSION = "1.0"

# --- small lexicons for cognition-relevant markers (Berisha/Pennebaker style) -
# Vagueness: indefinite nouns/pronouns that stand in for specific content.
INDEFINITE_WORDS = {
    "thing", "things", "stuff", "something", "anything", "nothing", "everything",
    "someone", "somebody", "anyone", "anybody", "everyone", "everybody",
    "somewhere", "anywhere", "somehow", "whatever", "whatchamacallit",
}
# Single-token hedges (multiword hedges handled by regex below).
HEDGE_WORDS = {
    "maybe", "perhaps", "possibly", "probably", "presumably", "somewhat",
    "roughly", "approximately", "apparently", "seemingly", "arguably",
    "guess", "suppose", "presume", "reckon", "likely", "unlikely",
}
HEDGE_PHRASES = re.compile(
    r"\b(sort of|kind of|i think|i guess|i mean|you know|more or less|"
    r"a little bit|i suppose|or something|i believe)\b", re.I)
# Disfluency fillers (usually stripped from curated transcripts; still recorded).
FILLER_WORDS = {"uh", "um", "er", "ah", "hmm", "mm", "erm", "uhh", "umm"}

# Closed-class (function-word) POS tags.
FUNCTION_POS = {"ADP", "AUX", "CCONJ", "DET", "PART", "PRON", "SCONJ"}
CONTENT_POS = {"NOUN", "PROPN", "VERB", "ADJ", "ADV"}
# Dependency relations that head a subordinate clause.
SUBORD_DEPS = {"advcl", "ccomp", "xcomp", "acl", "relcl", "csubj", "csubjpass"}
CLAUSE_DEPS = {"ROOT", "advcl", "ccomp", "xcomp", "acl", "relcl", "csubj",
               "csubjpass", "conj", "parataxis"}

_WORD = re.compile(r"[A-Za-z']+")

_nlp = None
_vader = None


# ---------------------------------------------------------------------------
# Optional backends (loaded once, guarded)
# ---------------------------------------------------------------------------

def _get_nlp(model: str):
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        # Keep tagger/parser/attribute_ruler/lemmatizer; NER is unused here.
        _nlp = spacy.load(model, disable=["ner"])
    except Exception as e:
        LOG.error("spaCy model %r unavailable (%s). Rich features will be blank. "
                  "Install with: python -m spacy download %s", model, e, model)
        _nlp = False
    return _nlp


def _get_vader():
    global _vader
    if _vader is not None:
        return _vader
    try:
        import nltk
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        from nltk.sentiment import SentimentIntensityAnalyzer
        _vader = SentimentIntensityAnalyzer()
    except Exception as e:
        LOG.warning("VADER unavailable (%s); sentiment columns will be blank.", e)
        _vader = False
    return _vader


# ---------------------------------------------------------------------------
# Length-robust lexical diversity
# ---------------------------------------------------------------------------

def mtld(tokens: list[str], threshold: float = 0.72) -> float:
    """Measure of Textual Lexical Diversity (length-robust; bidirectional mean)."""
    if len(tokens) < 50:
        return 0.0

    def _pass(toks: list[str]) -> float:
        factors = 0.0
        types: set[str] = set()
        count = 0
        for tok in toks:
            count += 1
            types.add(tok)
            if len(types) / count <= threshold:
                factors += 1
                types, count = set(), 0
        if count > 0:
            factors += (1 - len(types) / count) / (1 - threshold)
        return len(toks) / factors if factors > 0 else float(len(toks))

    return round((_pass(tokens) + _pass(tokens[::-1])) / 2, 2)


def mattr(tokens: list[str], window: int = 50) -> float:
    """Moving-Average Type-Token Ratio over a sliding window (length-robust)."""
    n = len(tokens)
    if n == 0:
        return 0.0
    if n < window:
        return round(len(set(tokens)) / n, 4)
    counts = Counter(tokens[:window])
    ttrs = [len(counts) / window]
    for i in range(window, n):
        out = tokens[i - window]
        counts[out] -= 1
        if counts[out] == 0:
            del counts[out]
        counts[tokens[i]] += 1
        ttrs.append(len(counts) / window)
    return round(sum(ttrs) / len(ttrs), 4)


# ---------------------------------------------------------------------------
# Per-document feature computation
# ---------------------------------------------------------------------------

def _depth(token) -> int:
    d = 0
    while token.head != token:
        d += 1
        token = token.head
        if d > 200:  # cycle guard (shouldn't happen on valid parses)
            break
    return d


def _ratio(num: int, den: int, nd: int = 4) -> float:
    return round(num / den, nd) if den else 0.0


def compute_features(doc, body: str) -> dict:
    alpha = [t for t in doc if t.is_alpha]
    n_words = len(alpha)
    low = [t.text.lower() for t in alpha]
    sents = list(doc.sents)
    n_sents = len(sents) or 1

    # POS / morphology
    pos = Counter(t.pos_ for t in alpha)
    fps = fpp = 0  # first-person singular / plural pronouns
    for t in alpha:
        if t.pos_ == "PRON":
            person = t.morph.get("Person")
            number = t.morph.get("Number")
            if person == ["1"]:
                if number == ["Sing"]:
                    fps += 1
                elif number == ["Plur"]:
                    fpp += 1
    function_words = sum(pos[p] for p in FUNCTION_POS)

    # Syntactic complexity (dependency parse)
    dep_dists = [abs(t.i - t.head.i) for t in doc
                 if t.dep_ != "punct" and t.head != t]
    mdd = round(sum(dep_dists) / len(dep_dists), 3) if dep_dists else 0.0
    tree_depths = [max((_depth(t) for t in s), default=0) for s in sents]
    mean_depth = round(sum(tree_depths) / len(tree_depths), 3) if tree_depths else 0.0
    subord = sum(1 for t in doc if t.dep_ in SUBORD_DEPS)
    clauses = sum(1 for t in doc if t.dep_ in CLAUSE_DEPS and t.pos_ in ("VERB", "AUX"))

    # Lexical diversity (length-robust)
    content_lemmas = [t.lemma_.lower() for t in alpha if t.pos_ in CONTENT_POS]
    hapax = sum(1 for _, c in Counter(low).items() if c == 1)

    # Cognition markers
    indef = sum(1 for w in low if w in INDEFINITE_WORDS)
    hedge = sum(1 for w in low if w in HEDGE_WORDS) + len(HEDGE_PHRASES.findall(body))
    filler = sum(1 for w in low if w in FILLER_WORDS)

    feats = {
        "n_words": n_words,
        "n_sentences": len(sents),
        # diversity
        "type_token_ratio": _ratio(len(set(low)), n_words),
        "mtld": mtld(low),
        "mattr_50": mattr(low),
        "content_ttr": _ratio(len(set(content_lemmas)), len(content_lemmas)),
        "hapax_ratio": _ratio(hapax, n_words),
        # pronouns / POS
        "pronoun_ratio": _ratio(pos["PRON"], n_words),
        "first_person_singular_ratio": _ratio(fps, n_words),
        "first_person_plural_ratio": _ratio(fpp, n_words),
        "i_to_we_ratio": round(fps / fpp, 3) if fpp else (float(fps) if fps else 0.0),
        "noun_ratio": _ratio(pos["NOUN"] + pos["PROPN"], n_words),
        "verb_ratio": _ratio(pos["VERB"], n_words),
        "adjective_ratio": _ratio(pos["ADJ"], n_words),
        "adverb_ratio": _ratio(pos["ADV"], n_words),
        "function_word_ratio": _ratio(function_words, n_words),
        # syntactic complexity
        "mean_dependency_distance": mdd,
        "mean_tree_depth": mean_depth,
        "subordination_ratio": _ratio(subord, n_sents, 4),
        "clauses_per_sentence": _ratio(clauses, n_sents, 3),
        # cognition markers
        "indefinite_noun_ratio": _ratio(indef, n_words, 5),
        "hedge_ratio": _ratio(hedge, n_words, 5),
        "filler_ratio": _ratio(filler, n_words, 5),
    }
    return feats


def _blank_features() -> dict:
    """Used when spaCy is unavailable so the columns still exist."""
    keys = ["n_words", "n_sentences", "type_token_ratio", "mtld", "mattr_50",
            "content_ttr", "hapax_ratio", "pronoun_ratio",
            "first_person_singular_ratio", "first_person_plural_ratio",
            "i_to_we_ratio", "noun_ratio", "verb_ratio", "adjective_ratio",
            "adverb_ratio", "function_word_ratio", "mean_dependency_distance",
            "mean_tree_depth", "subordination_ratio", "clauses_per_sentence",
            "indefinite_noun_ratio", "hedge_ratio", "filler_ratio"]
    return {k: "" for k in keys}


def _read_body(rel: str) -> str:
    path = C.ROOT / rel
    if not path.exists():
        return ""
    return "\n".join(l for l in path.read_text(encoding="utf-8", errors="replace").split("\n")
                     if not l.startswith("#")).strip()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(only_missing: bool = False, limit: int | None = None,
        model: str = "en_core_web_sm", n_process: int = 1) -> None:
    import pandas as pd

    meta = C.load_metadata()
    if meta.empty:
        LOG.warning("No metadata; nothing to extract.")
        return

    # existing features (for --only-missing and incremental merge)
    existing: dict[str, dict] = {}
    if FEATURES_CSV.exists():
        prev = pd.read_csv(FEATURES_CSV, dtype=str, keep_default_na=False)
        existing = {r["id"]: dict(r) for _, r in prev.iterrows()}

    todo = []
    for _, row in meta.iterrows():
        sid = row.get("id", "")
        if not sid:
            continue
        if only_missing and sid in existing:
            continue
        rel = row.get("clean_file_path", "")
        if rel:
            todo.append((sid, rel))
    if limit:
        todo = todo[:limit]
    if not todo:
        LOG.info("Nothing to do (%d already extracted).", len(existing))
        return

    nlp = _get_nlp(model)
    vader = _get_vader()
    model_label = f"{model}/{getattr(nlp, 'meta', {}).get('version', '?')}" if nlp else "none"
    LOG.info("Extracting features for %d transcripts (model=%s, vader=%s, n_process=%d).",
             len(todo), model_label, bool(vader), n_process)

    bodies = [_read_body(rel) for _, rel in todo]
    ids = [sid for sid, _ in todo]

    def _emit(sid, body, doc):
        feats = compute_features(doc, body) if doc is not None else _blank_features()
        if vader and body:
            vs = vader.polarity_scores(body[:20000])  # bound very long docs
            feats.update({"vader_compound": vs["compound"], "vader_pos": vs["pos"],
                          "vader_neg": vs["neg"], "vader_neu": vs["neu"]})
        else:
            feats.update({"vader_compound": "", "vader_pos": "",
                          "vader_neg": "", "vader_neu": ""})
        feats.update({"id": sid, "spacy_model": model_label,
                      "extractor_version": EXTRACTOR_VERSION})
        existing[sid] = feats

    n = 0
    if nlp:
        # stream with spaCy; skip empty bodies and the length guard for huge docs
        pairs = [(b[:1_000_000], (sid, b)) for sid, b in zip(ids, bodies)]
        for doc, (sid, body) in nlp.pipe(pairs, as_tuples=True, batch_size=64,
                                         n_process=n_process):
            try:
                _emit(sid, body, doc if body else None)
            except Exception as e:
                LOG.warning("Feature extraction failed for %s: %s", sid, e)
                _emit(sid, "", None)
            n += 1
            if n % 500 == 0:
                _save(existing)
                LOG.info("...%d processed", n)
    else:
        for sid, body in zip(ids, bodies):
            _emit(sid, body, None)
            n += 1

    _save(existing)
    LOG.info("DONE. Extracted features for %d transcripts (%d total in table).",
             n, len(existing))


def _save(rows_by_id: dict[str, dict]) -> None:
    import pandas as pd
    df = pd.DataFrame(list(rows_by_id.values()))
    # id + provenance first, rest alphabetical for stable diffs
    lead = ["id", "spacy_model", "extractor_version"]
    cols = lead + sorted(c for c in df.columns if c not in lead)
    df = df[cols]
    C.ensure_dirs()
    df.to_csv(FEATURES_CSV, index=False)
    try:
        df.to_parquet(FEATURES_PARQUET, index=False)
    except Exception as e:
        LOG.debug("Parquet write skipped (%s).", e)


def main():
    ap = argparse.ArgumentParser(description="Extract deterministic NLP features (cognition layer).")
    ap.add_argument("--only-missing", action="store_true",
                    help="skip transcripts already in linguistic_features.csv")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="en_core_web_sm",
                    help="spaCy model (en_core_web_sm/md/trf)")
    ap.add_argument("--n-process", type=int, default=1,
                    help="spaCy worker processes for nlp.pipe (parallel parsing)")
    args = ap.parse_args()
    run(args.only_missing, args.limit, args.model, args.n_process)


if __name__ == "__main__":
    main()
