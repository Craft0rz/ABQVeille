"""
External dead-man's-switch ping.

The alert of last resort: when the machine is off, the task is disabled, the
process hangs, or Gmail itself is what broke, nothing in this pipeline can tell
anyone. The external service notices the missing success ping instead.

Two providers, two protocols:
- UptimeRobot heartbeat (the Clairview account, Solo plan; alerts by email, SMS
  and Discord, routed ops@ -> fondateurs@): ONE url, any request = "alive".
  It has no start or fail signal, and a request to <url>/fail could just as
  well be read as alive, so for UptimeRobot only success is ever sent. A
  failure is signalled by silence.
- healthchecks.io (hc-ping.com): <url>/start and <url>/fail exist, and the
  request body is shown in its alert email, so a failure says why.
Any other host is treated like UptimeRobot: success only. Sending a "fail"
somewhere that might count it as alive is the one mistake this must not make.
"""
from urllib.parse import urlparse

from loguru import logger

FULL_PROTOCOL_HOSTS = ("hc-ping.com", "healthchecks.io")


def supports_start_fail(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in FULL_PROTOCOL_HOSTS)


def ping(url: str, signal: str = "", message: str = "") -> bool:
    """
    signal: "" = success / alive, "start" = run began, "fail" = nothing delivered.

    Returns True if a request was sent. Never raises: a failed ping must not
    break the run it reports on.
    """
    if not url:
        return False
    full = supports_start_fail(url)
    if signal and not full:
        return False  # silence is the failure signal for success-only providers
    target = url.rstrip("/") + (f"/{signal}" if signal else "")
    try:
        import requests
        if full:
            requests.post(target, data=(message or "")[:10000].encode("utf-8"), timeout=10)
        else:
            requests.get(target, timeout=10)
        return True
    except Exception as e:
        logger.warning(f"Heartbeat ping failed ({signal or 'success'}): {e}")
        return False
