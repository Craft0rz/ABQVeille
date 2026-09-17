#!/usr/bin/env python
"""
ABQ Veille Scientifique - Missed-Day Backfill

Finds content dates in the recoverable window that never got a digest (the
machine was off, the run crashed) and reprocesses them oldest-first.

Run this AFTER the daily run, so yesterday is already done and only real gaps
remain.

Usage:
    python run_backfill.py                  # report gaps, change nothing
    python run_backfill.py --run            # backfill the gaps
    python run_backfill.py --run --dry-run  # backfill but don't send email
    python run_backfill.py --lookback 3     # how far back to look

Exit codes:
    0 - Success (including "no gaps found")
    1 - One or more backfill runs failed
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from ABQ.src.config import DATA_DIR
from ABQ.src.orchestrator import PipelineRunner
from ABQ.src.utils.gap_detector import (
    DEFAULT_LOOKBACK_DAYS,
    describe_gaps,
    find_missing_dates,
)


def main():
    parser = argparse.ArgumentParser(description="Backfill missed digest days")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually backfill. Without this, only report what's missing.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Days to look back (default: {DEFAULT_LOOKBACK_DAYS}). Past the "
             f"default the RSS window has rolled off and a backfilled digest "
             f"covers only a fraction of that day.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline but don't send email",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Generate email but don't send",
    )
    args = parser.parse_args()

    missing = find_missing_dates(DATA_DIR, lookback_days=args.lookback)
    logger.info(describe_gaps(missing))

    if not missing:
        return 0

    if not args.run:
        logger.info("Reporting only. Re-run with --run to backfill these dates.")
        return 0

    failures = []
    for date_str in missing:
        logger.info(f"Backfilling {date_str}...")
        runner = PipelineRunner(
            date_str=date_str,
            dry_run=args.dry_run,
            skip_email=args.skip_email,
            force=False,
        )
        code = runner.run()
        if code != 0:
            logger.error(f"Backfill failed for {date_str} (exit {code})")
            failures.append(date_str)
        else:
            logger.success(f"Backfilled {date_str}")

    if failures:
        logger.error(f"Backfill failed for: {', '.join(failures)}")
        return 1

    logger.success(f"Backfilled {len(missing)} day(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
