"""
ABQ Veille Scientifique - Email Delivery

Email delivery modules for sending daily intelligence via Gmail API.
"""
from .gmail_auth import (
    GmailAuthManager,
    gmail_auth,
    SCOPES,
)
from .gmail_sender import (
    GmailSender,
    gmail_sender,
    EmailResult,
    SendReport,
)

__all__ = [
    # Authentication
    'GmailAuthManager',
    'gmail_auth',
    'SCOPES',
    # Sending
    'GmailSender',
    'gmail_sender',
    'EmailResult',
    'SendReport',
]
