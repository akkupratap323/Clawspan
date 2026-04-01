"""Google OAuth2 helper — shared by tools/google.py.

On first run: opens browser for OAuth consent, saves token.
On subsequent runs: loads saved token, refreshes if expired.
"""

import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_FILE

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
]

_CLIENT_CONFIG = {
    "installed": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


def get_credentials() -> Credentials:
    """Return valid Google credentials, refreshing or re-authorizing as needed."""
    creds = None

    if os.path.exists(GOOGLE_TOKEN_FILE):
        with open(GOOGLE_TOKEN_FILE) as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data.get("client_id", GOOGLE_CLIENT_ID),
            client_secret=data.get("client_secret", GOOGLE_CLIENT_SECRET),
            scopes=data.get("scopes", SCOPES),
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(_CLIENT_CONFIG, SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=True)

        with open(GOOGLE_TOKEN_FILE, "w") as f:
            json.dump({
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes or SCOPES),
            }, f, indent=2)

    return creds
