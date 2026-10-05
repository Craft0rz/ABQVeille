"""The outage alarm must work when everything else is broken.

2026-09-18 to 10-05: a rotated OAuth client secret left ABQ Veille hung at the
interactive Google login every weekday morning. No email, no exit, no alert -
the alerts went through the same broken Gmail, and the healthchecks.io ping
existed but had no URL. UAP had no external alarm at all. These tests pin the
two guarantees: an unattended run fails fast instead of hanging, and the
external switch only goes green when readers actually got a digest.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PKG = Path(__file__).parent.parent.name  # "UAP" or "ABQ-veille"
PKG = "ABQ" if PKG.startswith("ABQ") else PKG

import importlib  # noqa: E402

runner_mod = importlib.import_module(f"{PKG}.src.orchestrator.pipeline_runner")
auth_mod = importlib.import_module(f"{PKG}.src.delivery.gmail_auth")


# --- fail fast instead of hanging --------------------------------------------

def test_an_unattended_run_never_opens_a_browser_login(tmp_path, monkeypatch):
    (tmp_path / "client_secrets.json").write_text("{}")
    (tmp_path / "gmail_token.json").write_text("{}")
    mgr = auth_mod.GmailAuthManager.__new__(auth_mod.GmailAuthManager)
    mgr.credentials_dir = tmp_path
    mgr.client_secrets_path = tmp_path / "client_secrets.json"
    mgr.token_path = tmp_path / "gmail_token.json"
    mgr._credentials = None

    # A token that is expired and whose refresh is rejected - the 09-18 state.
    class Rejected:
        valid, expired, refresh_token = False, True, "r"

        def refresh(self, request):
            raise Exception("invalid_client: The provided client secret is invalid.")

    import google.oauth2.credentials as gcreds
    import google_auth_oauthlib.flow as gflow
    monkeypatch.setattr(gcreds.Credentials, "from_authorized_user_file",
                        classmethod(lambda cls, *a, **k: Rejected()))

    def no_browser(*a, **k):
        raise AssertionError("the unattended run tried to start a browser login")

    monkeypatch.setattr(gflow.InstalledAppFlow, "from_client_secrets_file", no_browser)

    with pytest.raises(auth_mod.GmailAuthError, match="client secret was rotated"):
        mgr.authenticate()


# --- the external switch -------------------------------------------------------

HC = "https://hc-ping.com/abc"                       # healthchecks.io: start/fail/body
UR = "https://heartbeat.uptimerobot.com/m123-xyz"    # UptimeRobot: success only


@pytest.fixture
def pings(monkeypatch):
    sent = []
    import requests
    monkeypatch.setattr(requests, "post",
                        lambda url, data=b"", timeout=None: sent.append((url, data.decode())))
    monkeypatch.setattr(requests, "get",
                        lambda url, timeout=None: sent.append((url, "")))
    monkeypatch.setattr(runner_mod.config.monitoring, "healthcheck_url", HC)
    return sent


def _runner(tmp_path, monkeypatch, emails_sent, fail_at=None):
    monkeypatch.setattr(runner_mod, "configure_logging", lambda *a, **k: None, raising=False)
    r = runner_mod.PipelineRunner(date_str="2026-10-04")
    r.state_file = tmp_path / "state.json"
    r.lock_file = tmp_path / "pipeline.lock"
    r._acquire_lock = lambda: True
    r._release_lock = lambda: None
    r._print_summary = lambda: None
    r._send_operator_alert = lambda *a, **k: None
    r.ai_stats = {}
    ok = lambda *a, **k: (True, 10)  # noqa: E731

    def boom(*a, **k):
        raise RuntimeError("Gmail token is invalid and cannot be refreshed")

    def send(*a, **k):
        if fail_at == "send":
            boom()
        r.state.emails_sent = emails_sent
        return True, SimpleNamespace(successful=emails_sent)

    for name in ("_stage_rss_fetch", "_stage_analysis"):
        setattr(r, name, ok)
    r._stage_health_check = lambda: None
    r._stage_model_preflight = lambda: True
    r._stage_email_generate = lambda: (True, "<html/>")
    r._stage_email_send = send
    return r


def _kinds(pings):
    return [url.rsplit("/", 1)[-1] if url.endswith(("/start", "/fail")) else "success"
            for url, _ in pings]


def test_green_only_when_the_digest_reached_readers(tmp_path, monkeypatch, pings):
    _runner(tmp_path, monkeypatch, emails_sent=24).run()
    assert _kinds(pings) == ["start", "success"]


def test_a_digest_that_reached_nobody_is_red(tmp_path, monkeypatch, pings):
    """Gmail not configured, every send failed, or the UAP prompt gate held it."""
    _runner(tmp_path, monkeypatch, emails_sent=0).run()
    assert _kinds(pings) == ["start", "fail"]


def test_a_crash_is_red_and_the_alert_says_why(tmp_path, monkeypatch, pings):
    _runner(tmp_path, monkeypatch, emails_sent=0, fail_at="send").run()
    assert _kinds(pings) == ["start", "fail"]
    assert "Gmail token is invalid" in pings[-1][1]


def test_no_url_means_no_ping_and_no_crash(tmp_path, monkeypatch, pings):
    monkeypatch.setattr(runner_mod.config.monitoring, "healthcheck_url", "")
    assert _runner(tmp_path, monkeypatch, emails_sent=24).run() == 0
    assert pings == []


# --- UptimeRobot: success only, silence is the failure ----------------------

def test_uptimerobot_gets_only_success_pings(tmp_path, monkeypatch, pings):
    monkeypatch.setattr(runner_mod.config.monitoring, "healthcheck_url", UR)
    _runner(tmp_path, monkeypatch, emails_sent=24).run()
    assert pings == [(UR, "")]


def test_uptimerobot_never_receives_a_request_on_failure(tmp_path, monkeypatch, pings):
    """A request to <url>/fail might be read as "alive". Silence is the signal."""
    monkeypatch.setattr(runner_mod.config.monitoring, "healthcheck_url", UR)
    _runner(tmp_path, monkeypatch, emails_sent=0).run()
    _runner(tmp_path, monkeypatch, emails_sent=0, fail_at="send").run()
    assert pings == []


@pytest.mark.parametrize("url,full", [
    ("https://hc-ping.com/abc", True),
    ("https://healthchecks.io/ping/abc", True),
    ("https://heartbeat.uptimerobot.com/m1", False),
    ("https://evil-hc-ping.com/abc", False),   # suffix match, not substring
    ("https://example.com/ping", False),
])
def test_only_known_full_protocol_hosts_get_start_and_fail(url, full):
    hb = importlib.import_module(f"{PKG}.src.utils.heartbeat")
    assert hb.supports_start_fail(url) is full
