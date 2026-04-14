import base64
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailClient:
    def __init__(self, credentials_path: str, token_path: str):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = None

    def authenticate(self):
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token...")
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"OAuth credentials file not found: {self.credentials_path}\n"
                        "Download it from Google Cloud Console and place it at the configured path.\n"
                        "Then run setup_credentials.py to complete the OAuth flow."
                    )
                logger.info("Starting OAuth2 flow (browser will open)...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
            logger.info("Token saved to %s", self.token_path)

        self.service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail API authenticated successfully")

    def fetch_meeting_notes(
        self, sender_filter: str, subject_prefix: str,
        after_timestamp: str = None, lookback_hours: int = 24,
        max_results: int = 10,
    ) -> list[dict]:
        if self.service is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        query = f'from:{sender_filter} subject:"{subject_prefix}"'
        if after_timestamp:
            after_dt = datetime.fromisoformat(after_timestamp)
            epoch = int(after_dt.timestamp())
            query += f" after:{epoch}"
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
            epoch = int(cutoff.timestamp())
            query += f" after:{epoch}"

        logger.info("Gmail search query: %s", query)

        results = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            logger.info("No new meeting notes found")
            return []

        logger.info("Found %d potential meeting note(s)", len(messages))
        return [{"message_id": msg["id"], "thread_id": msg["threadId"]} for msg in messages]

    def get_message(self, message_id: str) -> dict:
        if self.service is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        msg = self.service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {}
        for header in msg.get("payload", {}).get("headers", []):
            name = header["name"].lower()
            if name in ("from", "to", "subject", "date"):
                headers[name] = header["value"]

        body = self._extract_body(msg.get("payload", {}))

        return {
            "message_id": message_id,
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "date": headers.get("date", ""),
            "body": body,
        }

    def _extract_body(self, payload: dict) -> str:
        # Try to get plain text body first
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return self._decode_body(payload["body"]["data"])

        # Check parts for multipart messages
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return self._decode_body(part["body"]["data"])

        # Fallback: try HTML body and strip tags
        if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
            return self._decode_body(payload["body"]["data"])

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                return self._decode_body(part["body"]["data"])

        # Deep nested parts (multipart/alternative inside multipart/mixed)
        for part in payload.get("parts", []):
            body = self._extract_body(part)
            if body:
                return body

        return ""

    @staticmethod
    def _decode_body(data: str) -> str:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
