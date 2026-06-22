"""
classify_event_type.py — assign event_type + prepared/impromptu + Q&A + campaign.

Two backends:

  * RULES (default): fast, deterministic, transparent keyword/structure rules on
    the title and body. No external dependencies, no network. This is the
    recommended default for building the corpus.

  * LLM (--llm): routes each transcript through your LOCAL LM Studio model
    (see llm.py) for a judgment call on ambiguous cases. Opt-in only.

Fields written to metadata:
    event_type            one of EVENT_TYPES
    prepared_or_impromptu one of {prepared, impromptu, mixed, unknown}
    has_q_and_a           "1"/"0"
    campaign_or_official  {campaign, official, ""} (only set if confidently inferred)

Usage
-----
    python classify_event_type.py                 # rule-based, all rows
    python classify_event_type.py --only-missing  # skip already-classified rows
    python classify_event_type.py --llm           # use local LM Studio model
    python classify_event_type.py --llm --only-missing --limit 100
"""

from __future__ import annotations

import argparse
import re

import common as C

LOG = C.get_logger("classify")

# --- title keyword -> event_type (checked in order) -------------------------
TITLE_RULES = [
    (re.compile(r"\b(inaugural address|state of the union|farewell address|"
                r"address to the nation|address before|joint session)\b", re.I), "formal_address"),
    (re.compile(r"\b(campaign rally|rally|make america great)\b", re.I), "rally"),
    (re.compile(r"\b(news conference|press conference|press briefing|"
                r"briefing)\b", re.I), "press_conference"),
    (re.compile(r"\b(interview|conversation with)\b", re.I), "interview"),
    (re.compile(r"\b(presidential debate|debate)\b", re.I), "debate"),
    (re.compile(r"\b(roundtable)\b", re.I), "roundtable"),
    (re.compile(r"\b(town hall)\b", re.I), "town_hall"),
    (re.compile(r"\b(radio address|weekly address|fireside)\b", re.I), "radio_address"),
    (re.compile(r"\b(statement on signing|signing of|upon signing|"
                r"signing statement)\b", re.I), "signing_statement"),
    (re.compile(r"\b(question[- ]and[- ]answer|q\s*&\s*a|exchange with reporters)\b", re.I), "q_and_a"),
    (re.compile(r"\b(remarks)\b", re.I), "remarks"),
]

Q_LABEL = re.compile(r"^\s*(Q[:.\s]|QUESTION[:.]|REPORTER[:.]|MODERATOR[:.])", re.I | re.M)
A_LABEL = re.compile(r"^\s*(THE PRESIDENT|THE VICE PRESIDENT|PRESIDENT [A-Z]+)[:.]", re.M)
SPEAKER_LABEL = re.compile(r"^\s*[A-Z][A-Z .'-]{2,40}:", re.M)

CAMPAIGN_HINTS = re.compile(r"\b(rally|campaign|make america great|for president|"
                            r"vote for|on the campaign trail|caucus|primary night)\b", re.I)
OFFICIAL_HINTS = re.compile(r"\b(white house|oval office|rose garden|cabinet room|"
                            r"east room|briefing room|air force one)\b", re.I)


def _read_body(rel: str) -> str:
    path = C.ROOT / rel
    if not path.exists():
        return ""
    return "\n".join(l for l in path.read_text(encoding="utf-8", errors="replace").split("\n")
                     if not l.startswith("#")).strip()


def classify_rules(title: str, body: str) -> dict:
    event_type = "other"
    for rx, et in TITLE_RULES:
        if rx.search(title or ""):
            event_type = et
            break
    # if title gave nothing, sniff the body
    if event_type == "other" and body:
        head = body[:1500]
        for rx, et in TITLE_RULES:
            if rx.search(head):
                event_type = et
                break

    q_count = len(Q_LABEL.findall(body))
    has_qa = "1" if q_count >= 2 else "0"

    # prepared vs impromptu heuristic
    if event_type in ("formal_address", "radio_address", "signing_statement"):
        prep = "prepared"
    elif event_type in ("press_conference", "interview", "q_and_a", "debate", "town_hall"):
        prep = "impromptu" if has_qa == "1" else "mixed"
    elif event_type in ("rally", "remarks", "roundtable"):
        prep = "mixed"
    else:
        prep = "unknown"
    # remarks that contain a Q&A section are mixed
    if event_type == "remarks" and has_qa == "1":
        prep = "mixed"

    campaign = ""
    if CAMPAIGN_HINTS.search(title or "") or CAMPAIGN_HINTS.search(body[:1500]):
        campaign = "campaign"
    elif OFFICIAL_HINTS.search(body[:1500]):
        campaign = "official"

    return {
        "event_type": event_type,
        "prepared_or_impromptu": prep,
        "has_q_and_a": has_qa,
        "campaign_or_official": campaign,
    }


LLM_SYSTEM = (
    "You classify U.S. presidential transcripts. Given a title and an excerpt, "
    "return JSON with keys: event_type (one of: formal_address, rally, "
    "press_conference, interview, debate, remarks, roundtable, signing_statement, "
    "radio_address, town_hall, q_and_a, other), prepared_or_impromptu (prepared, "
    "impromptu, mixed, unknown), has_q_and_a (true/false), campaign_or_official "
    "(campaign, official, or unknown)."
)


def classify_llm(llm, title: str, body: str) -> dict:
    excerpt = body[:4000]
    prompt = f"TITLE: {title}\n\nEXCERPT:\n{excerpt}"
    data = llm.json_chat(prompt, system=LLM_SYSTEM, max_tokens=200)
    et = data.get("event_type", "")
    if et not in C.EVENT_TYPES:
        et = "other"
    prep = data.get("prepared_or_impromptu", "")
    if prep not in C.PREP_LABELS:
        prep = "unknown"
    qa = data.get("has_q_and_a", False)
    has_qa = "1" if (qa is True or str(qa).lower() in ("true", "yes", "1")) else "0"
    camp = str(data.get("campaign_or_official", "")).lower()
    camp = camp if camp in ("campaign", "official") else ""
    return {"event_type": et, "prepared_or_impromptu": prep,
            "has_q_and_a": has_qa, "campaign_or_official": camp}


def run(use_llm: bool, only_missing: bool, limit: int | None) -> None:
    df = C.load_metadata()
    if df.empty:
        LOG.warning("No metadata; nothing to classify.")
        return

    llm = None
    if use_llm:
        from llm import get_llm
        llm = get_llm()
        if not llm.is_available():
            LOG.error("LM Studio endpoint not reachable; falling back to rules. "
                      "Start LM Studio's server and load the model, or run without --llm.")
            llm = None

    n = 0
    for idx, row in df.iterrows():
        if limit and n >= limit:
            break
        if only_missing and (row.get("event_type") or "").strip():
            continue
        body = _read_body(row.get("clean_file_path", ""))
        title = row.get("title", "")
        if llm is not None:
            try:
                res = classify_llm(llm, title, body)
            except Exception as e:
                LOG.warning("LLM classify failed for %s (%s); using rules.",
                            row.get("id"), e)
                res = classify_rules(title, body)
        else:
            res = classify_rules(title, body)

        for k, v in res.items():
            if v != "":
                df.at[idx, k] = v
        n += 1

    C.save_metadata(df)
    LOG.info("Classified %d transcripts (%s backend).",
             n, "LLM" if llm is not None else "rules")


def main():
    ap = argparse.ArgumentParser(description="Classify event type & delivery mode.")
    ap.add_argument("--llm", action="store_true", help="use local LM Studio model")
    ap.add_argument("--only-missing", action="store_true",
                    help="only classify rows with empty event_type")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(args.llm, args.only_missing, args.limit)


if __name__ == "__main__":
    main()
