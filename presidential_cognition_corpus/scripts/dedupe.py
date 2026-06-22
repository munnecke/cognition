"""
dedupe.py — duplicate detection across the corpus.

We do NOT delete duplicates. We cluster them and mark one canonical member,
writing `duplicate_cluster_id` into the metadata for every row.

Methods (layered, cheap -> expensive):
  1. Exact URL match            -> same source_url
  2. Exact text hash            -> identical normalized body (sha1)
  3. Metadata near-duplicate    -> same president + same date + similar title
                                   (RapidFuzz token_set_ratio >= title threshold)
  4. Text near-duplicate        -> MinHash/LSH candidate pairs confirmed with a
                                   RapidFuzz body similarity check

Clusters are formed with a union-find over all matched pairs. Canonical member
of each cluster = highest quality_score, tie-broken by longest word_count, then
lexNS smallest id (stable).

Usage
-----
    python dedupe.py
    python dedupe.py --title-threshold 90 --text-threshold 0.85
"""

from __future__ import annotations

import argparse
import hashlib
import re

import common as C

LOG = C.get_logger("dedupe")


# --- union-find -------------------------------------------------------------
class UF:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _read_body(rel: str) -> str:
    path = C.ROOT / rel
    if not path.exists():
        return ""
    full = path.read_text(encoding="utf-8", errors="replace")
    # strip leading '#'-comment header
    lines = [ln for ln in full.split("\n") if not ln.startswith("#")]
    return "\n".join(lines).strip()


def _norm_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _shingles(text: str, k: int = 5):
    toks = re.findall(r"\w+", text.lower())
    return {" ".join(toks[i:i + k]) for i in range(max(0, len(toks) - k + 1))}


def run(title_threshold: int, text_threshold: float) -> None:
    df = C.load_metadata()
    if df.empty:
        LOG.warning("No metadata; nothing to dedupe.")
        return

    ids = list(df["id"])
    uf = UF(ids)
    by_id = {r["id"]: r for _, r in df.iterrows()}

    bodies: dict[str, str] = {}
    text_hash: dict[str, str] = {}
    for _id, row in by_id.items():
        body = _read_body(row.get("clean_file_path", ""))
        bodies[_id] = body
        if body:
            text_hash[_id] = hashlib.sha1(_norm_for_hash(body).encode()).hexdigest()

    # 1. exact URL
    url_groups: dict[str, list[str]] = {}
    for _id, row in by_id.items():
        u = (row.get("source_url") or "").strip()
        if u:
            url_groups.setdefault(u, []).append(_id)
    for grp in url_groups.values():
        for other in grp[1:]:
            uf.union(grp[0], other)

    # 2. exact text hash
    hash_groups: dict[str, list[str]] = {}
    for _id, h in text_hash.items():
        hash_groups.setdefault(h, []).append(_id)
    for grp in hash_groups.values():
        for other in grp[1:]:
            uf.union(grp[0], other)

    # 3. metadata near-dup: same president+date, similar title
    try:
        from rapidfuzz import fuzz
        have_rf = True
    except Exception:
        LOG.warning("rapidfuzz not installed; skipping fuzzy title/text steps.")
        have_rf = False

    if have_rf:
        pd_groups: dict[tuple, list[str]] = {}
        for _id, row in by_id.items():
            key = (row.get("president", ""), row.get("date", ""))
            if key[1]:  # only when we have a date
                pd_groups.setdefault(key, []).append(_id)
        for key, grp in pd_groups.items():
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    t1 = by_id[grp[i]].get("title", "")
                    t2 = by_id[grp[j]].get("title", "")
                    if fuzz.token_set_ratio(t1, t2) >= title_threshold:
                        uf.union(grp[i], grp[j])

    # 4. text near-dup via MinHash/LSH, confirmed by RapidFuzz
    try:
        from datasketch import MinHash, MinHashLSH
        have_ds = True
    except Exception:
        LOG.warning("datasketch not installed; skipping MinHash near-dup step.")
        have_ds = False

    if have_ds and have_rf:
        lsh = MinHashLSH(threshold=text_threshold, num_perm=128)
        minhashes: dict[str, "MinHash"] = {}
        for _id, body in bodies.items():
            if not body or len(body) < 200:
                continue
            mh = MinHash(num_perm=128)
            for sh in _shingles(body):
                mh.update(sh.encode("utf-8"))
            minhashes[_id] = mh
            lsh.insert(_id, mh)
        checked = set()
        for _id, mh in minhashes.items():
            for cand in lsh.query(mh):
                if cand == _id:
                    continue
                pair = tuple(sorted((_id, cand)))
                if pair in checked:
                    continue
                checked.add(pair)
                # confirm with a bounded RapidFuzz ratio on a prefix (speed)
                a, b = bodies[pair[0]][:5000], bodies[pair[1]][:5000]
                from rapidfuzz import fuzz
                if fuzz.ratio(a, b) >= text_threshold * 100:
                    uf.union(pair[0], pair[1])

    # form clusters
    clusters: dict[str, list[str]] = {}
    for _id in ids:
        clusters.setdefault(uf.find(_id), []).append(_id)

    # assign cluster ids + canonical flag
    df = df.set_index("id")
    if "is_canonical" not in df.columns:
        df["is_canonical"] = ""
    n_multi = 0
    for cid, (root, members) in enumerate(clusters.items()):
        cluster_label = f"clust_{cid:06d}"
        if len(members) > 1:
            n_multi += 1

        def sort_key(m):
            r = by_id[m]
            q = float(r.get("quality_score") or 0)
            wc = int(r.get("word_count") or 0)
            return (-q, -wc, m)

        canonical = sorted(members, key=sort_key)[0]
        for m in members:
            df.at[m, "duplicate_cluster_id"] = cluster_label
            df.at[m, "is_canonical"] = "1" if m == canonical else "0"

    df = df.reset_index()
    C.save_metadata(df)
    LOG.info("Dedupe complete: %d transcripts, %d clusters, %d multi-member clusters.",
             len(ids), len(clusters), n_multi)


def main():
    ap = argparse.ArgumentParser(description="Detect & cluster duplicate transcripts.")
    ap.add_argument("--title-threshold", type=int, default=90,
                    help="RapidFuzz token_set_ratio threshold for title match (0-100)")
    ap.add_argument("--text-threshold", type=float, default=0.85,
                    help="MinHash/RapidFuzz similarity threshold for body match (0-1)")
    args = ap.parse_args()
    run(args.title_threshold, args.text_threshold)


if __name__ == "__main__":
    main()
