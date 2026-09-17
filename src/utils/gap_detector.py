"""
Gap Detector - Missed-Day Detection and Backfill Planning

The runner only ever processes "yesterday". Nothing notices when a run doesn't
happen, so a day the machine is off is a day of news lost permanently and
silently. This module finds those holes.

Backfill is possible because a fetch pulls everything the feeds currently carry
-- several days' worth -- and only then filters down to the target date. So the
articles for a missed day are often still reachable the next time we fetch.

Coverage decays fast as the feed window rolls off. Measured on 2026-09-17 in
the sibling UAP project, whose pipeline is structurally identical and whose raw
fetches are retained (ABQ overwrites its article files with post-analysis
results, so the same measurement can't be taken here):

    day-1: 150 articles     day-4:  9 articles
    day-2:  86 articles     day-5:  4 articles
    day-3:  60 articles     day-6: 10 articles

ABQ's own window is likely narrower, not wider: its Quebec environmental
sources publish at much lower volume than UAP's news feeds.

Hence DEFAULT_LOOKBACK_DAYS = 3.
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from loguru import logger

# Past this many days the RSS window has rolled off (see module docstring).
DEFAULT_LOOKBACK_DAYS = 3

# A date is "done" when the pipeline wrote a digest for it.
DIGEST_MARKER = "digest.json"


def _parse(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def is_complete(data_dir: Path, date_str: str) -> bool:
    """True if a digest was produced for this date."""
    return (Path(data_dir) / date_str / DIGEST_MARKER).is_file()


def earliest_processed_date(data_dir: Path) -> Optional[str]:
    """
    Oldest date the project has ever produced a digest for.

    Used as a floor so a fresh clone (or the project's first days) doesn't
    report every date since the epoch as a gap.
    """
    dates = []
    for child in Path(data_dir).iterdir():
        if not child.is_dir():
            continue
        try:
            _parse(child.name)
        except ValueError:
            continue  # archive/, exports/, weekly/, etc.
        if (child / DIGEST_MARKER).is_file():
            dates.append(child.name)
    return min(dates) if dates else None


def find_missing_dates(
    data_dir: Path,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    today: Optional[str] = None,
) -> List[str]:
    """
    Find content dates in the recoverable window that have no digest.

    The window runs from (today - lookback_days) through (today - 1), since the
    most recent content date the pipeline can process is yesterday.

    Args:
        data_dir: Project data directory
        lookback_days: How far back to look. Beyond DEFAULT_LOOKBACK_DAYS the
            feed window has rolled off and backfill produces a misleadingly
            thin digest.
        today: Override for "today" (YYYY-MM-DD), for testing.

    Returns:
        Missing dates, oldest first, so a caller backfills in chronological
        order.
    """
    data_dir = Path(data_dir)
    now = _parse(today) if today else datetime.now()

    floor = earliest_processed_date(data_dir)
    if floor is None:
        logger.debug("No processed dates yet - nothing to backfill")
        return []
    floor_dt = _parse(floor)

    missing = []
    for offset in range(lookback_days, 0, -1):
        day = now - timedelta(days=offset)
        if day < floor_dt:
            continue  # before this project produced anything
        date_str = day.strftime("%Y-%m-%d")
        if not is_complete(data_dir, date_str):
            missing.append(date_str)

    return missing


def describe_gaps(missing: List[str], today: Optional[str] = None) -> str:
    """Human-readable gap summary, with a coverage caveat per date."""
    if not missing:
        return "No missed days in the recoverable window."

    now = _parse(today) if today else datetime.now()
    lines = [f"{len(missing)} missed day(s) found:"]
    for date_str in missing:
        age = (now - _parse(date_str)).days
        if age <= 2:
            note = "good feed coverage expected"
        elif age == 3:
            note = "partial coverage - feed window is rolling off"
        else:
            note = "POOR coverage - most of this day has left the feed window"
        lines.append(f"  {date_str}  ({age}d old, {note})")
    return "\n".join(lines)
