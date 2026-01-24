#!/usr/bin/env python
"""
ABQ Veille Scientifique - Main Entry Point

Run the complete daily intelligence pipeline for the
Association des Biologistes du Quebec.

Usage:
    python run_daily.py                    # Run for yesterday (default)
    python run_daily.py --date 2026-01-24  # Run for specific date
    python run_daily.py --dry-run          # Run without sending email
    python run_daily.py --force            # Ignore lock file

Exit codes:
    0 - Success
    1 - Pipeline error
    2 - Lock file error (concurrent run)
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ABQ.src.orchestrator import PipelineRunner


def main():
    parser = argparse.ArgumentParser(
        description="ABQ Veille Scientifique Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0  Success - pipeline completed
  1  Error - pipeline failed
  2  Lock error - another instance running
        """
    )
    parser.add_argument(
        "--date", "-d",
        help="Date to process (YYYY-MM-DD), defaults to yesterday"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without sending email"
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Generate email but don't send"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Ignore lock file and force run"
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Test mode: analyze only 2 articles, skip daily summary"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="ABQ Veille Scientifique 1.0.0"
    )

    args = parser.parse_args()

    runner = PipelineRunner(
        date_str=args.date,
        dry_run=args.dry_run,
        skip_email=args.skip_email,
        force=args.force,
        test_mode=args.test
    )

    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
