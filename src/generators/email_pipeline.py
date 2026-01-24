"""
Email Pipeline - End-to-end email generation from DailyDigest.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.utils.storage import storage
from ABQ.src.config import DATA_DIR
from ABQ.src.generators.email_compiler import EmailCompiler, EmailContext
from ABQ.src.generators.email_renderer import EmailRenderer

class EmailPipeline:
    """Generates complete email from DailyDigest."""

    def __init__(self):
        self.compiler = EmailCompiler()
        self.renderer = EmailRenderer()

    def generate(self, date_str=None, save_html=True) -> Tuple[str, Optional[Path]]:
        """
        Generate email for a date.

        Args:
            date_str: Date string (YYYY-MM-DD), defaults to today
            save_html: Whether to save HTML to file

        Returns:
            Tuple of (html_string, saved_path)
        """
        # Default to today
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"Generating email for {date_str}")

        # Load digest from storage
        digest = storage.load_digest(date_str)
        if not digest:
            error_msg = f"No digest found for {date_str}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Compile to EmailContext
        context = self.compiler.compile(digest)

        # Render to HTML
        html = self.renderer.render(context)

        # Optionally save to data/YYYY-MM-DD/email.html
        saved_path = None
        if save_html:
            output_path = DATA_DIR / date_str / "email.html"
            saved_path = self.renderer.render_to_file(context, output_path)

        logger.success(
            f"Generated email for {date_str}: {len(html)} bytes"
            + (f", saved to {saved_path}" if saved_path else "")
        )

        return html, saved_path

    def preview(self, date_str=None) -> EmailContext:
        """
        Generate preview context without rendering.

        Args:
            date_str: Date string (YYYY-MM-DD), defaults to today

        Returns:
            EmailContext for inspection
        """
        # Default to today
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"Generating preview for {date_str}")

        # Load digest from storage
        digest = storage.load_digest(date_str)
        if not digest:
            error_msg = f"No digest found for {date_str}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Compile to EmailContext
        context = self.compiler.compile(digest)

        logger.info(
            f"Preview context: {context.article_count} articles, "
            f"{len(context.executive_summary)} in summary"
        )

        return context

def generate_daily_email(date_str=None):
    """
    Convenience function to generate daily email.

    Args:
        date_str: Date string (YYYY-MM-DD), defaults to today

    Returns:
        Tuple of (html_string, saved_path)
    """
    pipeline = EmailPipeline()
    return pipeline.generate(date_str)
