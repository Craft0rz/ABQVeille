"""
Pipeline Runner

Orchestrates the complete daily intelligence pipeline for ABQ.
"""
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ABQ.src.config import DATA_DIR, LOGS_DIR, CONFIG_DIR
from ABQ.src.collectors import fetch_all_rss
from ABQ.src.models import ArticleModel
from ABQ.src.utils import storage
from ABQ.src.utils.feed_health import FeedHealthChecker, format_health_report
from ABQ.src.analyzers import AnalysisPipeline
from ABQ.src.generators import EmailPipeline
from ABQ.src.delivery import gmail_sender, gmail_auth
from ABQ.src.config import config

from .execution_state import ExecutionState, PipelineStage
from .log_config import configure_logging


class LockFileError(Exception):
    """Raised when lock file indicates concurrent run."""
    pass


class PipelineRunner:
    """Orchestrates the complete daily intelligence pipeline."""

    def __init__(
        self,
        date_str: Optional[str] = None,
        dry_run: bool = False,
        skip_email: bool = False,
        force: bool = False,
        test_mode: bool = False
    ):
        """
        Initialize pipeline runner.

        Args:
            date_str: Date to process (YYYY-MM-DD), defaults to yesterday
            dry_run: If True, skip email sending
            skip_email: If True, generate but don't send email
            force: If True, ignore lock file
            test_mode: If True, minimize AI usage (2 articles, no daily summary)
        """
        # Default to yesterday for daily database building
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.date_str = date_str or yesterday
        self.dry_run = dry_run
        self.skip_email = skip_email or dry_run
        self.force = force
        self.test_mode = test_mode

        # Paths
        self.data_dir = DATA_DIR / self.date_str
        self.log_dir = LOGS_DIR
        self.lock_file = LOGS_DIR / "pipeline.lock"
        self.state_file = DATA_DIR / self.date_str / "execution_state.json"

        # State
        self.state = ExecutionState(date_str=self.date_str, started_at=datetime.now())

        # AI analysis stats from the analysis stage (used for outage detection).
        # {analyzed, failed, skipped, filtered_low_impact}
        self.ai_stats: dict = {}

    def _acquire_lock(self) -> bool:
        """Acquire execution lock to prevent concurrent runs."""
        if self.force:
            logger.warning("Force mode: ignoring lock file")
            return True

        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    lock_data = json.load(f)
                locked_at = datetime.fromisoformat(lock_data.get('started_at', ''))
                pid = lock_data.get('pid', 'unknown')

                # Check if lock is stale (older than 1 hour)
                age = (datetime.now() - locked_at).total_seconds()
                if age > 3600:
                    logger.warning(f"Stale lock file (age: {age/60:.1f} min), removing")
                    self.lock_file.unlink()
                else:
                    raise LockFileError(
                        f"Pipeline already running (PID: {pid}, started: {locked_at})"
                    )
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("Invalid lock file, removing")
                self.lock_file.unlink()

        # Create lock file
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, 'w') as f:
            json.dump({
                'pid': os.getpid(),
                'started_at': datetime.now().isoformat(),
                'date': self.date_str
            }, f)
        return True

    def _release_lock(self):
        """Release execution lock."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove lock file: {e}")

    def _stage_health_check(self) -> Tuple[bool, dict]:
        """Stage 0: Check feed health and apply automatic fixes."""
        logger.info("=" * 60)
        logger.info("STAGE 0: Feed Health Check")
        logger.info("=" * 60)

        try:
            # Load feeds config
            feeds_config_path = CONFIG_DIR / "feeds.json"
            with open(feeds_config_path) as f:
                config_data = json.load(f)
                feeds = config_data.get("feeds", [])

            # Run health check
            checker = FeedHealthChecker(timeout=20)
            report = checker.check_all_feeds(feeds)

            # Log report
            logger.info(format_health_report(report))

            # Apply automatic fixes
            if report["fixed"]:
                fixes_applied = checker.apply_fixes(feeds_config_path, report)
                logger.success(f"Applied {fixes_applied} automatic fixes")

            # Log warnings for down feeds
            if report["down"]:
                logger.warning(f"{len(report['down'])} feeds are currently down")
                for feed in report["down"]:
                    logger.warning(f"  • {feed['name']}: {feed.get('issue', 'unknown')}")

            if report["degraded"]:
                logger.warning(f"{len(report['degraded'])} feeds are degraded")
                for feed in report["degraded"]:
                    logger.warning(f"  • {feed['name']}: {feed.get('issue', 'unknown')}")

            logger.info("Feed health check complete")
            return True, report

        except Exception as e:
            logger.exception(f"Feed health check failed: {e}")
            # Don't fail the pipeline, continue with RSS fetch
            logger.warning("Continuing with RSS fetch despite health check failure")
            return False, {}

    def _stage_rss_fetch(self) -> Tuple[bool, int]:
        """Stage 1: Fetch RSS feeds."""
        stage = self.state.start_stage(PipelineStage.RSS_FETCH)

        try:
            articles = fetch_all_rss()

            if not articles:
                logger.warning("No articles fetched from RSS feeds")
                self.state.complete_stage(stage, success=True, items=0)
                return True, 0

            # Convert to ArticleModel
            article_models = []
            for a in articles:
                model = ArticleModel(
                    url=a.url,
                    title=a.title,
                    summary=a.summary,
                    published=a.published,
                    source_name=a.source_name,
                    source_url=a.source_url,
                    category=a.category,
                    language=a.language,
                    author=a.author,
                    tags=a.tags if a.tags else []
                )
                article_models.append(model)

            # Save articles
            storage.save_articles(article_models, self.date_str)

            self.state.total_articles_fetched = len(article_models)
            self.state.complete_stage(stage, success=True, items=len(article_models))

            logger.info(f"RSS fetch complete: {len(article_models)} articles")
            return True, len(article_models)

        except Exception as e:
            logger.exception(f"RSS fetch failed: {e}")
            self.state.complete_stage(stage, success=False, error=str(e))
            return False, 0

    def _stage_analysis(self) -> Tuple[bool, int]:
        """Stage 2: Content extraction and relevancy scoring."""
        stage = self.state.start_stage(PipelineStage.RELEVANCY_SCORE)

        try:
            pipeline = AnalysisPipeline(
                extract_content=True,
                extraction_delay=1.0,
                extraction_limit=50,
                test_mode=self.test_mode
            )
            digest = pipeline.process_daily(self.date_str)

            # Capture AI stats so run() can tell an outage (all articles errored)
            # apart from a genuine slow news day (nothing relevant).
            if pipeline.ai_analyst:
                self.ai_stats = pipeline.ai_analyst.get_stats()

            if not digest:
                logger.warning("No digest generated from analysis")
                self.state.complete_stage(stage, success=True, items=0)
                return True, 0

            self.state.relevant_articles = digest.total_articles
            self.state.complete_stage(
                stage, success=True, items=digest.total_articles,
                details={'categories': digest.by_category}
            )

            logger.info(f"Analysis complete: {digest.total_articles} relevant articles")
            return True, digest.total_articles

        except Exception as e:
            logger.exception(f"Analysis failed: {e}")
            self.state.complete_stage(stage, success=False, error=str(e))
            return False, 0

    def _stage_email_generate(self) -> Tuple[bool, str]:
        """Stage 3: Generate email HTML."""
        stage = self.state.start_stage(PipelineStage.EMAIL_GENERATE)

        try:
            pipeline = EmailPipeline()
            html_content, email_path = pipeline.generate(self.date_str, save_html=True)

            if not html_content:
                raise ValueError("No email content generated")

            self.state.complete_stage(
                stage, success=True, items=1,
                details={'html_size': len(html_content)}
            )

            logger.info(f"Email generated: {len(html_content)} bytes")
            return True, html_content

        except Exception as e:
            logger.exception(f"Email generation failed: {e}")
            self.state.complete_stage(stage, success=False, error=str(e))
            return False, ""

    def _stage_email_send(self, html_content: str) -> Tuple[bool, dict]:
        """Stage 4: Send email via Gmail API."""
        stage = self.state.start_stage(PipelineStage.EMAIL_SEND)

        if self.skip_email:
            logger.info("Skipping email send (dry-run or skip-email mode)")
            self.state.complete_stage(
                stage, success=True, items=0,
                details={'skipped': True}
            )
            return True, {'skipped': True}

        # Check if Gmail is configured
        if not gmail_auth.has_client_secrets():
            logger.warning("Gmail credentials not found - skipping email send")
            logger.info("To configure Gmail: copy client_secrets.json to ABQ/credentials/")
            self.state.complete_stage(
                stage, success=True, items=0,
                details={'not_configured': True, 'reason': 'missing_credentials'}
            )
            return True, {'not_configured': True}

        if not config.email.recipient_emails:
            logger.warning("No recipient emails configured - skipping email send")
            self.state.complete_stage(
                stage, success=True, items=0,
                details={'not_configured': True, 'reason': 'no_recipients'}
            )
            return True, {'not_configured': True}

        try:
            # Build subject line
            subject = f"{config.email.subject_prefix} {self.date_str}"

            # Send via Gmail
            report = gmail_sender.send_daily_intelligence(
                html_content=html_content,
                subject=subject
            )

            self.state.emails_sent = report.successful
            self.state.emails_failed = report.failed

            self.state.complete_stage(
                stage, success=True, items=report.successful,
                details={
                    'sent': report.successful,
                    'failed': report.failed,
                    'recipients': [r.recipient for r in report.results]
                }
            )

            if report.failed > 0:
                logger.warning(f"Email send partial: {report.successful} sent, {report.failed} failed")
            else:
                logger.info(f"Email sent successfully to {report.successful} recipients")

            return True, {'sent': report.successful, 'failed': report.failed}

        except Exception as e:
            logger.exception(f"Email send failed: {e}")
            self.state.complete_stage(stage, success=False, error=str(e))
            return False, {'error': str(e)}

    def _send_operator_alert(self, subject: str, body: str) -> None:
        """Send an operational health alert to the operator (NOT the member list).

        Used so an AI outage or degradation can never again produce a silent
        no-send. No-op (log only) in dry-run/skip-email mode, or when the alert
        address / Gmail credentials are unavailable.
        """
        logger.critical(f"OPERATOR ALERT: {subject}")

        if self.skip_email:
            logger.info("dry-run/skip-email mode: not sending operator alert email")
            return

        alert_to = config.email.alert_email
        if not alert_to:
            logger.error("No ALERT_EMAIL/SENDER_EMAIL configured - cannot send operator alert")
            return
        if not gmail_auth.has_client_secrets():
            logger.error("Gmail not configured - cannot send operator alert")
            return

        try:
            html = "<pre style=\"font-family:sans-serif;white-space:pre-wrap\">" + body + "</pre>"
            result = gmail_sender.send(
                to=alert_to,
                subject=f"{config.email.subject_prefix} ALERTE - {subject}",
                html_content=html,
                from_name=config.email.sender_name,
            )
            if result.success:
                logger.info(f"Operator alert sent to {alert_to}")
            else:
                logger.error(f"Operator alert send failed: {result.error}")
        except Exception as e:
            logger.exception(f"Failed to send operator alert: {e}")

    def _ping_healthcheck(self, endpoint: str = "") -> None:
        """Ping the external dead-man's-switch (healthchecks.io or compatible).

        This is the ONLY thing that can catch the pipeline not running at all
        (machine off, scheduled task disabled, crash before analysis): if the
        external service stops receiving pings, IT alerts the operator.

        endpoint: "" = success, "start" = run began, "fail" = run failed.
        Best-effort and never raises. Skipped in dry-run/skip-email mode.
        """
        url = config.monitoring.healthcheck_url
        if not url:
            return
        if self.skip_email:
            logger.debug(f"dry-run/skip-email: skipping healthcheck ping ({endpoint or 'success'})")
            return

        ping_url = url.rstrip("/") + (f"/{endpoint}" if endpoint else "")
        try:
            import requests
            requests.get(ping_url, timeout=10)
            logger.debug(f"Healthcheck pinged: {endpoint or 'success'}")
        except Exception as e:
            # A failed heartbeat ping must never break the run.
            logger.warning(f"Healthcheck ping failed ({endpoint or 'success'}): {e}")

    def run(self) -> int:
        """
        Run the complete pipeline.

        Returns:
            Exit code (0 = success, 1 = failure, 2 = lock error)
        """
        # Configure logging
        configure_logging(self.log_dir, self.date_str)

        logger.info("=" * 60)
        logger.info(f"ABQ Veille Scientifique Pipeline - {self.date_str}")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("DRY RUN MODE - No emails will be sent")
        if self.test_mode:
            logger.info("TEST MODE - AI limited to 2 articles, no daily summary")

        try:
            # Acquire lock
            self._acquire_lock()

            # Signal the external dead-man's-switch that a run has started.
            self._ping_healthcheck("start")

            # Stage 0: Feed Health Check (non-blocking)
            self._stage_health_check()

            # Stage 1: RSS Fetch
            success, count = self._stage_rss_fetch()
            if not success:
                raise RuntimeError("RSS fetch stage failed")

            if count == 0:
                logger.warning("No articles to process, exiting early")
                self._ping_healthcheck()  # ran to completion, just nothing to process
                self.state.mark_complete(success=True, exit_code=0)
                return 0

            # Stage 2: Analysis
            success, count = self._stage_analysis()
            if not success:
                raise RuntimeError("Analysis stage failed")

            if count == 0:
                ai = self.ai_stats or {}
                # Distinguish an AI outage from a genuine slow news day.
                # Outage: articles reached the model but every one errored
                # (e.g. retired model ID -> 404). A slow day has failed == 0.
                if ai.get("failed", 0) > 0 and ai.get("analyzed", 0) == 0:
                    logger.critical(
                        f"AI analysis outage: {ai.get('failed')} articles failed, "
                        f"0 analyzed - no digest could be built for {self.date_str}"
                    )
                    self._send_operator_alert(
                        subject=f"Aucun digest envoye pour {self.date_str} - panne IA",
                        body=(
                            f"Le pipeline ABQ Veille du {self.date_str} n'a produit AUCUN "
                            f"article pertinent parce que l'analyse IA a echoue sur tous les "
                            f"articles ({ai.get('failed')} echecs, 0 analyses).\n\n"
                            f"C'est presque toujours un probleme de modele/API Claude "
                            f"(ex: identifiant de modele retire -> 404).\n"
                            f"Verifier logs/errors_{self.date_str}.log pour l'erreur exacte.\n\n"
                            f"AUCUN courriel n'a ete envoye a la liste de diffusion."
                        ),
                    )
                    self.state.error_message = "AI analysis outage (all articles failed)"
                    self._ping_healthcheck("fail")  # ran, but failed - external switch shows red
                    self.state.mark_complete(success=False, exit_code=1)
                    return 1

                logger.warning("No relevant articles found (genuine slow day), skipping email")
                self._ping_healthcheck()  # ran fine, genuinely nothing to send
                self.state.mark_complete(success=True, exit_code=0)
                return 0

            # Stage 3: Email Generation
            success, html = self._stage_email_generate()
            if not success:
                raise RuntimeError("Email generation stage failed")

            # Stage 4: Email Send
            success, report = self._stage_email_send(html)
            if not success:
                raise RuntimeError("Email send stage failed")

            # Non-blocking heads-up: digest went out, but AI failed on some
            # articles (partial degradation worth knowing about).
            ai = self.ai_stats or {}
            if ai.get("failed", 0) > 0:
                logger.warning(f"AI analysis had {ai['failed']} failure(s) this run: {ai}")
                self._send_operator_alert(
                    subject=f"Analyse IA degradee pour {self.date_str} (digest envoye quand meme)",
                    body=(
                        f"Le digest du {self.date_str} a ete envoye, mais l'analyse IA a "
                        f"echoue sur {ai['failed']} article(s) (stats: {ai}).\n"
                        f"Verifier logs/errors_{self.date_str}.log."
                    ),
                )

            # Complete
            self._ping_healthcheck()  # success heartbeat for the external switch
            self.state.mark_complete(success=True, exit_code=0)
            logger.success(f"Pipeline completed successfully in {self.state.get_duration():.1f}s")

            return 0

        except LockFileError as e:
            logger.error(f"Lock file error: {e}")
            self.state.error_message = str(e)
            self.state.mark_complete(success=False, exit_code=2)
            return 2

        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            self.state.error_message = str(e)
            self._ping_healthcheck("fail")  # crashed - external switch shows red
            self.state.mark_complete(success=False, exit_code=1)
            return 1

        finally:
            # Save state and release lock
            self.state.save(self.state_file)
            self._release_lock()

            # Print summary
            self._print_summary()

    def _print_summary(self):
        """Print execution summary."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("Resume de l'execution / Execution Summary")
        logger.info("=" * 60)
        logger.info(f"  Date:              {self.date_str}")
        logger.info(f"  Duree:             {self.state.get_duration():.1f}s")
        logger.info(f"  Statut:            {'SUCCES' if self.state.success else 'ECHEC'}")
        logger.info(f"  Articles recuperes:{self.state.total_articles_fetched}")
        logger.info(f"  Articles pertinents:{self.state.relevant_articles}")
        logger.info(f"  Courriels envoyes: {self.state.emails_sent}")
        if self.state.emails_failed:
            logger.info(f"  Courriels echoues: {self.state.emails_failed}")
        if self.state.error_message:
            logger.info(f"  Erreur:            {self.state.error_message}")
        logger.info("=" * 60)
