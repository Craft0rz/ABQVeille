#!/usr/bin/env python3
"""
Send an "alive" ping to the external dead-man's-switch outside a pipeline run.

Used by run_daily_automated.bat on weekends, when the digest is skipped by
design. UptimeRobot heartbeats are interval-based, not cron-based, so a silent
Friday-to-Monday would page every Saturday. The weekend ping is honest: it
proves the machine is on and the scheduled task fires, which is what the
heartbeat watches; the digest itself is only expected on weekdays.

Usage: python scripts/heartbeat.py "weekend skip"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ABQ.src.config import config  # noqa: E402
from ABQ.src.utils.heartbeat import ping  # noqa: E402

if __name__ == "__main__":
    reason = " ".join(sys.argv[1:]) or "alive"
    sent = ping(config.monitoring.healthcheck_url, "", reason)
    print(f"heartbeat: {'sent' if sent else 'not sent (no HEALTHCHECK_URL)'} - {reason}")
