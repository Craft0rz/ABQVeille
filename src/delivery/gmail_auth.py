"""
Gmail Authentication Manager

Handles OAuth 2.0 authentication for Gmail API access.
Manages token storage, refresh, and credential validation.
"""
from pathlib import Path
from typing import Optional
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from ABQ.src.config import CREDENTIALS_DIR

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']


class GmailAuthManager:
    """Manages Gmail OAuth 2.0 authentication."""

    def __init__(
        self,
        credentials_dir: Optional[Path] = None,
        client_secrets_file: str = 'client_secrets.json',
        token_file: str = 'gmail_token.json'
    ):
        """
        Initialize authentication manager.

        Args:
            credentials_dir: Directory for credential files
            client_secrets_file: OAuth client secrets filename
            token_file: Token storage filename
        """
        self.credentials_dir = credentials_dir or CREDENTIALS_DIR
        self.client_secrets_path = self.credentials_dir / client_secrets_file
        self.token_path = self.credentials_dir / token_file
        self._credentials = None

    def has_client_secrets(self) -> bool:
        """Check if client secrets file exists."""
        return self.client_secrets_path.exists()

    def has_valid_token(self) -> bool:
        """Check if valid token exists."""
        if not self.token_path.exists():
            return False
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), SCOPES
            )
            return creds and creds.valid
        except Exception:
            return False

    def authenticate(self, force_refresh: bool = False) -> bool:
        """
        Authenticate with Gmail API.

        Args:
            force_refresh: Force re-authentication

        Returns:
            True if authentication successful
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not self.has_client_secrets():
            logger.error(f"Client secrets not found: {self.client_secrets_path}")
            logger.info("Download from Google Cloud Console -> APIs & Services -> Credentials")
            return False

        creds = None

        # Load existing token
        if self.token_path.exists() and not force_refresh:
            try:
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), SCOPES
                )
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")

        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Token refreshed successfully")
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}")
                    creds = None

            if not creds:
                # Run OAuth flow
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("New authentication successful")

            # Save token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())
            logger.info(f"Token saved to {self.token_path}")

        self._credentials = creds
        return True

    def get_credentials(self):
        """Get current credentials (authenticate if needed)."""
        if not self._credentials:
            self.authenticate()
        return self._credentials

    def get_service(self):
        """Get Gmail API service object."""
        from googleapiclient.discovery import build

        creds = self.get_credentials()
        if not creds:
            raise RuntimeError("Not authenticated. Run authenticate() first.")

        return build('gmail', 'v1', credentials=creds)

    def revoke(self) -> bool:
        """Revoke current credentials."""
        import requests

        if not self._credentials:
            return True

        try:
            requests.post(
                'https://oauth2.googleapis.com/revoke',
                params={'token': self._credentials.token},
                headers={'content-type': 'application/x-www-form-urlencoded'}
            )
            if self.token_path.exists():
                self.token_path.unlink()
            self._credentials = None
            logger.info("Credentials revoked successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to revoke credentials: {e}")
            return False


# Global singleton instance
gmail_auth = GmailAuthManager()
