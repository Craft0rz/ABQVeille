#!/usr/bin/env python3
"""
Weekly publisher audit: which outlets reaching the digest look like content farms.

Usage:
    python scripts/audit_publishers.py                    # report, last 7 days
    python scripts/audit_publishers.py --days 14
    python scripts/audit_publishers.py --email            # email the report to ALERT_EMAILS
                                                          # (only when something needs review)
    python scripts/audit_publishers.py --decide "EnergyNow=allowed" --note "only CA energy source"
    python scripts/audit_publishers.py --decide "AD HOC NEWS=blocked" --note "stock blurbs"

Scheduled: run_daily_automated.bat runs it with --email on Mondays.
See src/reporting/publisher_audit.py for the signals and why it never blocks
on its own.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ABQ.src.config import CONFIG_DIR, DATA_DIR  # noqa: E402
from ABQ.src.reporting.publisher_audit import (  # noqa: E402
    audit_publishers, format_report, load_register, needs_review, publisher_from_title,
    record_decision,
)

REGISTER = CONFIG_DIR / "publisher_review.json"


def _publisher_of(article: dict) -> str:
    """
    Google News items name the outlet in the title suffix; a direct feed IS the
    outlet. Reading the suffix off a direct feed's headline invents publishers
    out of any headline containing " - ".
    """
    if "news.google.com" in (article.get("url") or "") + (article.get("source_url") or ""):
        return publisher_from_title(article.get("title", ""))
    return article.get("source_name") or ""


def collect_records(days: int, end: date) -> list:
    """Stored articles for the `days` days ending `end`, marked if they reached the digest."""
    records = []
    for back in range(days):
        day = (end - timedelta(days=back)).isoformat()
        day_dir = DATA_DIR / day
        if not day_dir.is_dir():
            continue
        in_digest = set()
        digest_path = day_dir / "digest.json"
        if digest_path.exists():
            digest = json.loads(digest_path.read_text(encoding="utf-8"))
            for arts in (digest.get("articles") or {}).values():
                in_digest.update(a.get("title", "") for a in arts)
        for f in day_dir.glob("articles_*.json"):
            for a in json.loads(f.read_text(encoding="utf-8")):
                # Only what passed the date filter: the folder also holds
                # weeks-old items Google News re-serves on every fetch.
                if (a.get("published") or "")[:10] != day:
                    continue
                title = a.get("title", "")
                records.append({"date": day, "title": title, "in_digest": title in in_digest,
                                "publisher": _publisher_of(a)})
    return records


def _email_operator(subject: str, body: str) -> None:
    """To ALERT_EMAIL (operator), never the member list. Same path as the pipeline's alerts."""
    from ABQ.src.config import config
    from ABQ.src.delivery import gmail_sender, gmail_auth
    to = config.email.alert_email
    if not to or not gmail_auth.has_client_secrets():
        print("No ALERT_EMAIL / Gmail credentials - report printed only")
        return
    html = "<pre style=\"font-family:sans-serif;white-space:pre-wrap\">" + body + "</pre>"
    result = gmail_sender.send(to=to, subject=f"{config.email.subject_prefix} {subject}",
                               html_content=html, from_name=config.email.sender_name)
    print(f"Operator email: {'sent' if result.success else 'FAILED ' + str(result.error)}")


def main() -> int:
    p = argparse.ArgumentParser(description="Audit the publishers feeding the digest")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--email", action="store_true",
                   help="Email the report to the operator if anything needs review")
    p.add_argument("--decide", metavar='"Publisher=allowed|blocked"')
    p.add_argument("--note", default="")
    args = p.parse_args()

    if args.decide:
        publisher, _, decision = args.decide.rpartition("=")
        if not publisher.strip():
            p.error('--decide takes "Publisher=allowed" or "Publisher=blocked"')
        record_decision(REGISTER, publisher.strip(), decision.strip().lower(), args.note)
        print(f"Recorded: {publisher.strip()} -> {decision.strip().lower()}")
        return 0

    # Yesterday is the last day with a complete digest.
    end = date.today() - timedelta(days=1)
    stats = audit_publishers(collect_records(args.days, end))
    register = load_register(REGISTER)
    report = format_report(stats, register, args.days, client="ABQ Veille")
    print(report)

    if args.email and needs_review(stats, register):
        from ABQ.src.utils.alerts import send_alert
        send_alert(
            subject=f"Publisher audit: {len(needs_review(stats, register))} publisher(s) to review",
            body=report,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
