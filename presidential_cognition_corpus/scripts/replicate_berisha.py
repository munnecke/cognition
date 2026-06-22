"""
replicate_berisha.py — reproduce Berisha et al. (2015) as a pipeline validation.

Berisha, Wang, LaCross & Liss (2015), "Tracking Discourse Complexity Preceding
Alzheimer's Disease Diagnosis," J Alzheimers Dis 45(3):959-963. doi:10.3233/JAD-142763
(documents/nihms-1062581.pdf).

Their method, reproduced here:
  1. Take APP *news conferences* for a president, chronologically ordered.
  2. Keep ONLY the president's spontaneous answers (segment_speaker), dropping the
     prepared statement, reporters' questions, topic headers, [bracket] notes.
  3. Restrict to the first 1,400 words; keep only transcripts that reach 1,400.
  4. Per transcript, count: unique words (Lancaster-stemmed), non-specific nouns
     (contain "thing"), fillers {well, so, basically, actually, literally, um, ah},
     and low-imageability verbs.
  5. Drop per-feature outliers (>2 SD), regress each feature on chronological index.

Their published result (Table 1):
  Reagan  — unique words  R=-0.446 (p=0.002)   NS+fillers R=+0.358 (p=0.017)
  Bush 41 — no significant trend on any feature

Recovering Reagan's negative unique-word trend and positive NS+filler trend (and
Bush's null) validates our collection + segmentation + feature extraction end to end.

Usage:  python replicate_berisha.py [--president reagan] [--max-words 1400]
"""

from __future__ import annotations

import argparse
import glob
import re

import numpy as np
from scipy import stats
from nltk.stem import LancasterStemmer

import common as C
import segment_speaker as S

LOG = C.get_logger("replicate_berisha")

_WORD = re.compile(r"[A-Za-z']+")
_STEM = LancasterStemmer()

# Berisha's filler set (their Methods, citing Le et al.).
FILLERS = {"well", "so", "basically", "actually", "literally", "um", "ah"}
# Low-imageability verbs "common in semantic dementia" (Bird et al. 2000, the 14
# they cite). NOTE: approximate light-verb set — confirm against Bird et al. 2000
# before treating LI-verb numbers as exact. LI verbs showed NO significant trend
# in the original, so this does not affect the headline validation.
LI_VERBS = {"be", "have", "do", "get", "give", "go", "make", "come",
            "take", "put", "move", "turn", "bring", "keep"}


def berisha_features(pres_text: str, max_words: int = 1400) -> dict | None:
    words = _WORD.findall(pres_text.lower())
    if len(words) < max_words:
        return None                       # below Berisha's length threshold
    words = words[:max_words]
    stems = [_STEM.stem(w) for w in words]
    ns_nouns = sum(1 for w in words if "thing" in w)
    fillers = sum(1 for w in words if w in FILLERS)
    return {
        "unique_words": len(set(stems)),
        "ns_nouns": ns_nouns,
        "fillers": fillers,
        "ns_plus_fillers": ns_nouns + fillers,
        "li_verbs": sum(1 for w in words if w in LI_VERBS),
    }


def _read_body(path: str) -> str:
    return "\n".join(l for l in open(path, encoding="utf-8", errors="replace").read().split("\n")
                     if not l.startswith("#"))


def collect_conferences(president: str, max_words: int) -> list[dict]:
    """Return chronologically-sorted feature rows for a president's news conferences."""
    paths = sorted(glob.glob(f"{C.SPEECHES}/*_{president}_*news-conference*.txt"))
    rows = []
    for p in paths:
        # date is the leading YYYY-MM-DD of the filename
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p)
        date = m.group(1) if m else ""
        ans = S.president_answers(_read_body(p))
        feats = berisha_features(ans, max_words)
        if feats is None:
            continue
        feats["date"] = date
        rows.append(feats)
    rows.sort(key=lambda r: r["date"])
    return rows


def regress(rows: list[dict], feature: str) -> dict:
    """Pearson correlation of `feature` vs chronological index, after >2 SD outlier drop."""
    idx = np.arange(len(rows))
    vals = np.array([r[feature] for r in rows], dtype=float)
    # per-feature outlier removal (>2 SD from mean), as in Berisha et al.
    keep = np.abs(vals - vals.mean()) <= 2 * vals.std()
    xi, yi = idx[keep], vals[keep]
    if len(xi) < 3:
        return {"R": float("nan"), "p": float("nan"), "n": int(keep.sum()), "dropped": int((~keep).sum())}
    r, p = stats.pearsonr(xi, yi)
    return {"R": round(float(r), 3), "p": round(float(p), 4),
            "n": int(keep.sum()), "dropped": int((~keep).sum())}


# Berisha's published coefficients, for side-by-side comparison.
PUBLISHED = {
    "reagan": {"unique_words": (-0.446, 0.002), "ns_plus_fillers": (0.358, 0.017),
               "li_verbs": (0.032, 0.835), "n": 46},
    "bush41": {"unique_words": (-0.098, 0.343), "ns_plus_fillers": (0.053, 0.608),
               "li_verbs": (-0.099, 0.333), "n": 101},
}


def _verdict(r: float, p: float, alpha: float = 0.05) -> str:
    """Scientific verdict for a trend: direction only matters when significant."""
    if p is None or p != p or p >= alpha:   # NaN or non-significant
        return "null"
    return "sig-pos" if r > 0 else "sig-neg"


def run(president: str, max_words: int) -> None:
    rows = collect_conferences(president, max_words)
    LOG.info("%s: %d news conferences with >= %d answer-words.",
             president, len(rows), max_words)
    if not rows:
        LOG.warning("No qualifying conferences for %s (still collecting?).", president)
        return

    print(f"\n=== Berisha replication — {president} "
          f"({rows[0]['date']} .. {rows[-1]['date']}, n={len(rows)}) ===")
    pub = PUBLISHED.get(president, {})
    print(f"{'feature':18} {'ours R':>8} {'ours p':>8}   {'Berisha R':>10} {'Berisha p':>9}   verdict match")
    print("-" * 78)
    for feat in ("unique_words", "ns_plus_fillers", "li_verbs"):
        res = regress(rows, feat)
        pr, pp = pub.get(feat, (None, None))
        # Compare the SCIENTIFIC verdict, not raw coefficients: a null is a null
        # regardless of the sign of a non-significant coefficient.
        mark = ""
        if pr is not None:
            mark = "OK" if _verdict(res["R"], res["p"]) == _verdict(pr, pp) else "DIFF"
        pr_s = f"{pr:+.3f}" if pr is not None else "  -  "
        pp_s = f"{pp:.3f}" if pp is not None else "  -  "
        print(f"{feat:18} {res['R']:>+8.3f} {res['p']:>8.4f}   {pr_s:>10} {pp_s:>9}   "
              f"{_verdict(res['R'], res['p']):>7}   {mark}")
    print("(verdict = sig-neg / sig-pos / null at alpha=0.05; >2SD outliers dropped per paper)")


def main():
    ap = argparse.ArgumentParser(description="Replicate Berisha et al. 2015 as a validation.")
    ap.add_argument("--president", nargs="*", default=["reagan", "bush41"])
    ap.add_argument("--max-words", type=int, default=1400)
    args = ap.parse_args()
    for pres in args.president:
        run(pres, args.max_words)


if __name__ == "__main__":
    main()
