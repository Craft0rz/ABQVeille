"""
Email Renderer - Renders EmailContext to HTML using Jinja2.
"""
from pathlib import Path
from typing import Optional
from loguru import logger
from jinja2 import Environment, FileSystemLoader, select_autoescape

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.config import TEMPLATES_DIR
from ABQ.src.generators.email_compiler import EmailContext
from ABQ.src.generators.template_filters import FILTERS

class EmailRenderer:
    """Renders email templates using Jinja2."""

    def __init__(self, template_dir=None, template_name='daily.html'):
        self.template_dir = template_dir or (TEMPLATES_DIR / 'email')
        self.template_name = template_name

        # Initialize Jinja2 environment with FileSystemLoader
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Register custom filters from FILTERS dict
        for filter_name, filter_func in FILTERS.items():
            self.env.filters[filter_name] = filter_func

        logger.info(f"Initialized EmailRenderer with template dir: {self.template_dir}")

    def render(self, context: EmailContext) -> str:
        """
        Render EmailContext to HTML string.

        Args:
            context: EmailContext with all template data

        Returns:
            HTML string
        """
        logger.info(f"Rendering email template: {self.template_name}")

        try:
            template = self.env.get_template(self.template_name)

            # Convert dataclass to dict for template rendering
            context_dict = {
                'date': context.date,
                'subject': context.subject,
                'logo_url': context.logo_url,
                'article_count': context.article_count,
                'source_count': context.source_count,
                'executive_summary': context.executive_summary,
                'ai_executive_summary': context.ai_executive_summary,
                'categories': context.categories,
                'sources': context.sources,
                'generated_at': context.generated_at,
                'unsubscribe_url': context.unsubscribe_url,
                'preferences_url': context.preferences_url,
            }

            html = template.render(**context_dict)
            logger.success(f"Rendered email: {len(html)} bytes")
            return html

        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            raise

    def render_to_file(self, context: EmailContext, output_path: Path) -> Path:
        """
        Render and save to file.

        Args:
            context: EmailContext with all template data
            output_path: Path to save HTML file

        Returns:
            Path to saved file
        """
        html = self.render(context)

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"Saved email to: {output_path}")
        return output_path
