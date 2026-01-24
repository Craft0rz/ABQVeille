"""
Gmail Sender

Composes and sends HTML emails via Gmail API.
"""
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.delivery.gmail_auth import gmail_auth
from ABQ.src.config import config


@dataclass
class EmailResult:
    """Result of a single email send attempt."""
    recipient: str
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: Optional[datetime] = None


@dataclass
class SendReport:
    """Report of batch email sending."""
    total: int = 0
    successful: int = 0
    failed: int = 0
    results: List[EmailResult] = field(default_factory=list)

    def add_result(self, result: EmailResult):
        self.results.append(result)
        self.total += 1
        if result.success:
            self.successful += 1
        else:
            self.failed += 1


class GmailSender:
    """Sends emails via Gmail API."""

    def __init__(self):
        """Initialize sender with authentication."""
        self.auth = gmail_auth
        self._service = None

    @property
    def service(self):
        """Lazy-load Gmail service."""
        if not self._service:
            self._service = self.auth.get_service()
        return self._service

    def _create_message(
        self,
        to: str,
        subject: str,
        html_content: str,
        from_name: Optional[str] = None
    ) -> dict:
        """
        Create email message for Gmail API.

        Args:
            to: Recipient email address
            subject: Email subject line
            html_content: HTML body content
            from_name: Display name for sender

        Returns:
            Gmail API message dict
        """
        message = MIMEMultipart('alternative')

        # Set headers
        sender = config.email.sender_email
        if from_name:
            message['From'] = f"{from_name} <{sender}>"
        else:
            message['From'] = sender
        message['To'] = to
        message['Subject'] = subject

        # Create plain text version (fallback)
        plain_text = self._html_to_plain(html_content)
        part1 = MIMEText(plain_text, 'plain')
        part2 = MIMEText(html_content, 'html')

        message.attach(part1)
        message.attach(part2)

        # Encode for Gmail API
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return {'raw': raw}

    def _html_to_plain(self, html: str) -> str:
        """Convert HTML to plain text (simple version)."""
        import re
        # Remove HTML tags
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'</p>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        # Decode entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        from_name: Optional[str] = None
    ) -> EmailResult:
        """
        Send a single email.

        Args:
            to: Recipient email
            subject: Subject line
            html_content: HTML body
            from_name: Optional sender display name

        Returns:
            EmailResult with success/failure info
        """
        try:
            message = self._create_message(to, subject, html_content, from_name)

            result = self.service.users().messages().send(
                userId='me',
                body=message
            ).execute()

            logger.info(f"Email sent to {to}, message ID: {result['id']}")

            return EmailResult(
                recipient=to,
                success=True,
                message_id=result['id'],
                sent_at=datetime.now()
            )

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return EmailResult(
                recipient=to,
                success=False,
                error=str(e)
            )

    def send_batch(
        self,
        recipients: List[str],
        subject: str,
        html_content: str,
        from_name: Optional[str] = None
    ) -> SendReport:
        """
        Send email to multiple recipients.

        Args:
            recipients: List of email addresses
            subject: Subject line
            html_content: HTML body
            from_name: Optional sender display name

        Returns:
            SendReport with all results
        """
        report = SendReport()

        for recipient in recipients:
            result = self.send(recipient, subject, html_content, from_name)
            report.add_result(result)

        logger.info(
            f"Batch send complete: {report.successful}/{report.total} successful"
        )

        return report

    def send_daily_intelligence(
        self,
        html_content: str,
        subject: str,
        recipients: Optional[List[str]] = None
    ) -> SendReport:
        """
        Send daily intelligence email to configured recipients.

        Args:
            html_content: Generated HTML email content
            subject: Email subject
            recipients: Override recipient list (uses config if None)

        Returns:
            SendReport
        """
        if recipients is None:
            recipients = config.email.recipient_emails

        return self.send_batch(
            recipients=recipients,
            subject=subject,
            html_content=html_content,
            from_name=config.email.sender_name
        )


# Global singleton instance
gmail_sender = GmailSender()
