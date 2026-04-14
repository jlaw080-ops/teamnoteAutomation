import base64
import logging
import re
from html.parser import HTMLParser
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
        plain = self._find_part(payload, "text/plain")
        if plain:
            return plain

        # Fallback: get HTML body and convert to plain text
        html = self._find_part(payload, "text/html")
        if html:
            return self._html_to_text(html)

        return ""

    def _find_part(self, payload: dict, mime_type: str) -> str | None:
        """Recursively search for a part with the given MIME type."""
        if payload.get("mimeType") == mime_type:
            data = payload.get("body", {}).get("data")
            if data:
                return self._decode_body(data)

        for part in payload.get("parts", []):
            result = self._find_part(part, mime_type)
            if result:
                return result

        return None

    @staticmethod
    def _decode_body(data: str) -> str:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML to plain text, preserving line breaks."""
        # Replace block-level tags with newlines
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"</(?:p|div|tr|li|h[1-6]|blockquote)>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</(?:td|th)>", "\t", text, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode common HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&nbsp;", " ")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")

        # Clean up whitespace: collapse multiple spaces on same line
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse 3+ consecutive newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip leading/trailing whitespace per line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text.strip()
