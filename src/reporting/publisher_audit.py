"""
Publisher audit - find content-farm publishers before they shape the digest.

30 of the 37 feeds are Google News searches, which pull from whatever outlet
matches: 621 distinct publishers in the 14 days to 2026-10-04. Nobody adds
those publishers, so vetting a feed when it is added cannot catch them. AD HOC
NEWS (auto-generated stock blurbs) arrived through the existing GPC search and
fed the same lead into six consecutive briefs.

So the audit runs on what actually arrived, and flags three signals:
- REPUBLISHED: the same title stored on more than one day. Each copy carries a
  fresh publication date, so it passes the date filter and reads as new news.
  The strongest signal, and the one that produced the repeats.
- TEMPLATED: most titles open the same way once numbers are masked
  ("Genuine Parts stock gains #.## percent..."). Machine-generated copy.
- INFLUENTIAL (listed, never flagged): the publishers that most often reach
  the digest. Influence is not a fault, so it never asks for a decision; it is
  there so a farm that slipped past the other two signals is still visible.

It only flags. A rule that auto-blocked templated titles would also block the
Bank of Canada's rate announcements. Decisions live in a review register
(config/publisher_review.json); a reviewed publisher drops off the report, and
"blocked" ones are dropped by the pipeline before scoring.

The core (audit_publishers, publisher_from_title, the register helpers) takes
plain records and paths so it can be reused by other pipelines.
"""
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Thresholds. Calibrated on 2026-09-21..10-04 (3 to review of 327 publishers):
# AD HOC NEWS 89% templated, EnergyNow 52% republished. 4 template words missed
# AD HOC NEWS ("Genuine Parts stock gains" vs "...stock costs"). Small samples
# are noise, hence the minimums.
REPUBLISHED_MIN_SHARE, REPUBLISHED_MIN_TITLES = 0.2, 2
TEMPLATED_MIN_SHARE, TEMPLATED_MIN_ARTICLES = 0.7, 5
INFLUENTIAL_MIN_DIGEST = 3
TEMPLATE_WORDS = 3

DECISIONS = ("allowed", "blocked")


def publisher_from_title(title: str) -> str:
    """The outlet Google News appends as " - Publisher", or '' if none."""
    head, sep, tail = (title or "").rpartition(" - ")
    return tail.strip() if sep and head.strip() else ""


def _headline(title: str) -> str:
    """Title without its publisher suffix."""
    head, sep, tail = (title or "").rpartition(" - ")
    return head if sep and head.strip() else (title or "")


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9#]+", " ", text.lower()).strip()


def _template(headline: str) -> str:
    """Opening words with every number masked, so "1.69 percent" == "1.19 percent"."""
    masked = re.sub(r"\d+(?:[.,]\d+)*", "#", headline)
    return " ".join(_normalise(masked).split()[:TEMPLATE_WORDS])


@dataclass
class PublisherStats:
    publisher: str
    articles: int = 0
    in_digest: int = 0
    days_seen: int = 0
    republished_titles: int = 0
    republished_share: float = 0.0
    templated_share: float = 0.0
    examples: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


def audit_publishers(records: Iterable[dict]) -> List[PublisherStats]:
    """
    Score every publisher in `records`.

    Each record is {"date": "YYYY-MM-DD", "title": str, "in_digest": bool} and
    optionally "publisher" (derived from the title suffix when absent). Pass
    only articles PUBLISHED on their date: feeds re-serve weeks-old items on
    every fetch, and counting those reads an old article as a re-dated one. Returns
    all publishers, flagged ones first, then by digest influence.
    """
    titles_by_pub: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    counts: Dict[str, Counter] = defaultdict(Counter)
    raw: Dict[str, List[str]] = defaultdict(list)

    for r in records:
        pub = (r.get("publisher") or publisher_from_title(r.get("title", ""))).strip()
        if not pub:
            continue
        headline = _headline(r.get("title", ""))
        titles_by_pub[pub][_normalise(headline)].add(r.get("date"))
        counts[pub]["articles"] += 1
        counts[pub]["in_digest"] += 1 if r.get("in_digest") else 0
        raw[pub].append(headline)

    out = []
    for pub, titles in titles_by_pub.items():
        s = PublisherStats(publisher=pub, articles=counts[pub]["articles"],
                           in_digest=counts[pub]["in_digest"])
        s.days_seen = len({d for ds in titles.values() for d in ds})
        s.republished_titles = sum(1 for ds in titles.values() if len(ds) > 1)
        s.republished_share = s.republished_titles / len(titles)
        # On DISTINCT headlines: a title stored on three days is one headline,
        # and counting it three times made it look like a template.
        distinct = sorted(set(raw[pub]))
        templates = Counter(_template(h) for h in distinct)
        s.templated_share = sum(c for c in templates.values() if c > 1) / len(distinct)
        s.examples = sorted(set(raw[pub]))[:3]

        if (s.republished_titles >= REPUBLISHED_MIN_TITLES
                and s.republished_share >= REPUBLISHED_MIN_SHARE):
            s.flags.append(f"REPUBLISHED {s.republished_titles} titles on 2+ days "
                           f"({s.republished_share:.0%})")
        if len(distinct) >= TEMPLATED_MIN_ARTICLES and s.templated_share >= TEMPLATED_MIN_SHARE:
            s.flags.append(f"TEMPLATED {s.templated_share:.0%} of titles share an opening")
        out.append(s)

    out.sort(key=lambda s: (not s.flags, -s.in_digest, -s.articles, s.publisher.lower()))
    return out


# --- review register ---------------------------------------------------------

def load_register(path: Path) -> Dict[str, dict]:
    """{publisher_lowercase: {"publisher", "decision", "reviewed", "note"}}"""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k.lower(): {"publisher": k, **v} for k, v in data.items()}


def blocked_publishers(path: Path) -> frozenset:
    """Lowercased names the pipeline must drop. Unreadable register = block nothing."""
    try:
        reg = load_register(path)
    except Exception:
        return frozenset()
    return frozenset(k for k, v in reg.items() if v.get("decision") == "blocked")


def record_decision(path: Path, publisher: str, decision: str, note: str = "",
                    today: Optional[date] = None) -> None:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    # Keep one entry per publisher regardless of the casing it was entered in.
    for key in [k for k in data if k.lower() == publisher.lower()]:
        del data[key]
    data[publisher] = {"decision": decision,
                       "reviewed": (today or date.today()).isoformat(),
                       "note": note}
    path.write_text(json.dumps(dict(sorted(data.items(), key=lambda kv: kv[0].lower())),
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def needs_review(stats: List[PublisherStats], register: Dict[str, dict]) -> List[PublisherStats]:
    """Flagged publishers nobody has decided on yet, most digest influence first."""
    return [s for s in stats if s.flags and s.publisher.lower() not in register]


def top_influencers(stats: List[PublisherStats], n: int = 8) -> List[PublisherStats]:
    """Publishers most often in the digest. Informational: influence is not a fault."""
    ranked = sorted((s for s in stats if s.in_digest >= INFLUENTIAL_MIN_DIGEST),
                    key=lambda s: -s.in_digest)
    return ranked[:n]


def format_report(stats: List[PublisherStats], register: Dict[str, dict],
                  days: int, client: str = "") -> str:
    pending = needs_review(stats, register)
    blocked = sorted(v["publisher"] for v in register.values() if v.get("decision") == "blocked")
    lines = [
        f"Publisher audit{f' - {client}' if client else ''}: last {days} days, "
        f"{len(stats)} publishers, {len(pending)} need a decision.",
        "",
    ]
    for s in pending:
        lines += [
            f"{s.publisher}  ({s.articles} articles over {s.days_seen} days, "
            f"{s.in_digest} in digest)",
            *[f"   ! {f}" for f in s.flags],
            *[f"   e.g. {e[:110]}" for e in s.examples],
            "",
        ]
    if not pending:
        lines += ["Nothing new to review.", ""]
    influencers = top_influencers(stats)
    if influencers:
        lines += ["Most digest appearances (for awareness, no action needed):"]
        for s in influencers:
            decided = register.get(s.publisher.lower(), {}).get("decision", "not reviewed")
            lines.append(f"   {s.in_digest:3d}  {s.publisher}  [{decided}]")
        lines.append("")
    lines += [
        "Decide with:",
        '  python scripts/audit_publishers.py --decide "<Publisher>=allowed" --note "why"',
        '  python scripts/audit_publishers.py --decide "<Publisher>=blocked" --note "why"',
        "Blocked publishers are dropped before scoring from the next run on.",
        "",
        f"Currently blocked: {', '.join(blocked) or 'none'}",
    ]
    return "\n".join(lines)
