"""
Gmail API Setup Script

Interactive script to set up Gmail API authentication.
Run this once to authorize the application.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ABQ.src.delivery.gmail_auth import GmailAuthManager, SCOPES
from ABQ.src.config import CREDENTIALS_DIR


def main():
    print("=" * 60)
    print("Gmail API Setup")
    print("=" * 60)
    print()

    auth = GmailAuthManager()

    # Check for client secrets
    if not auth.has_client_secrets():
        print("ERROR: Client secrets file not found!")
        print()
        print("To set up Gmail API:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create or select a project")
        print("3. Enable the Gmail API")
        print("4. Create OAuth 2.0 credentials (Desktop app)")
        print("5. Download the JSON file")
        print(f"6. Save as: {auth.client_secrets_path}")
        print()
        print("Download it from Google Cloud Console -> APIs & Services -> Credentials (same OAuth client as UAP).")
        return 1

    print(f"Client secrets found: {auth.client_secrets_path}")
    print()

    # Check existing token
    if auth.has_valid_token():
        print("Valid token already exists!")
        response = input("Re-authenticate? (y/N): ").strip().lower()
        if response != 'y':
            print("Setup complete. Token is valid.")
            return 0
        force_refresh = True
    else:
        force_refresh = False

    # Run authentication
    print()
    print("Starting OAuth flow...")
    print("A browser window will open for authorization.")
    print()

    if auth.authenticate(force_refresh=force_refresh, interactive=True):
        print()
        print("=" * 60)
        print("SUCCESS! Gmail API is now configured.")
        print("=" * 60)
        print()
        print("You can now run the daily intelligence email sender.")
        return 0
    else:
        print()
        print("ERROR: Authentication failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
