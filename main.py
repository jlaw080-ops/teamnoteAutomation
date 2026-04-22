#!/usr/bin/env python3
"""Gmail-to-Obsidian Meeting Notes Automation.

Polls Gmail for meeting notes from Genspark and creates Obsidian markdown notes.
Designed to run via Windows Task Scheduler every 5 minutes.

Usage:
    python main.py [--config config.yaml] [--dry-run]
"""

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config_loader import load_config
from src.email_parser import parse_email
from src.gmail_client import GmailClient
from src.note_builder import build_note, generate_filename, save_note
from src.state_manager import StateManager
from src.summarizer import summarize_meeting_notes

LOCK_FILE = "running.lock"
LOCK_TIMEOUT_SECONDS = 300  # 5 minutes


def setup_logging(config: dict):
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    log_file = log_config.get("log_file", "logs/automation.log")

    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def acquire_lock() -> bool:
    lock_path = Path(LOCK_FILE)
    if lock_path.exists():
        age = time.time() - lock_path.stat().st_mtime
        if age < LOCK_TIMEOUT_SECONDS:
            return False
        logging.warning("Stale lock file detected (age: %.0fs), removing", age)
        lock_path.unlink()
    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock():
    lock_path = Path(LOCK_FILE)
    if lock_path.exists():
        lock_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Gmail-to-Obsidian Meeting Notes Automation")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Parse emails but don't create note files")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")

    if not acquire_lock():
        logger.info("Another instance is already running. Exiting.")
        sys.exit(0)

    try:
        _run(config, args.dry_run, logger)
    except Exception:
        logger.exception("Unexpected error during execution")
        sys.exit(1)
    finally:
        release_lock()


def _run(config: dict, dry_run: bool, logger: logging.Logger):
    gmail_config = config["gmail"]
    obsidian_config = config["obsidian"]
    polling_config = config["polling"]
    state_config = config["state"]
    summarization_config = config.get("summarization", {})

    # Initialize state manager
    state = StateManager(
        state_file=state_config["state_file"],
        max_tracked_ids=state_config.get("max_tracked_ids", 500),
    )

    # Authenticate Gmail
    client = GmailClient(
        credentials_path=gmail_config["credentials_path"],
        token_path=gmail_config["token_path"],
    )
    client.authenticate()

    # Fetch new meeting notes
    messages = client.fetch_meeting_notes(
        sender_filter=gmail_config["sender_filter"],
        subject_prefix=gmail_config["subject_prefix"],
        after_timestamp=state.last_poll_utc,
        lookback_hours=polling_config.get("lookback_hours", 24),
        max_results=polling_config.get("max_results", 10),
    )

    created_count = 0
    skipped_count = 0

    for msg_info in messages:
        message_id = msg_info["message_id"]

        if state.is_processed(message_id):
            logger.debug("Skipping already processed message: %s", message_id)
            skipped_count += 1
            continue

        try:
            # Fetch full message
            full_msg = client.get_message(message_id)
            subject = full_msg["subject"]
            body = full_msg["body"]

            logger.info("Processing: %s", subject)

            # Parse email content
            parsed = parse_email(subject, body)

            # Summarize meeting notes via Claude API
            if summarization_config.get("enabled") and summarization_config.get("api_key"):
                logger.info("Summarizing: %s", parsed["title"])
                summarized_body = summarize_meeting_notes(
                    body=parsed["raw_body"],
                    title=parsed["title"],
                    date=parsed["date"],
                    duration=parsed["duration"],
                    api_key=summarization_config["api_key"],
                    model=summarization_config.get("model", "claude-sonnet-4-20250514"),
                )
                parsed["raw_body"] = summarized_body
                parsed["sections"] = {}  # Use summarized raw_body directly

            if dry_run:
                logger.info("[DRY RUN] Would create note: %s", parsed["title"])
                logger.info("[DRY RUN] Date: %s, Duration: %s", parsed["date"], parsed["duration"])
                logger.info("[DRY RUN] Preview:\n%s", parsed["raw_body"][:500])
                state.mark_processed(message_id)
                created_count += 1
                continue

            # Build note content
            note_content = build_note(
                template_path=obsidian_config["template_path"],
                parsed_data=parsed,
            )

            # Generate filename and save
            filename = generate_filename(
                parsed_data=parsed,
                filename_format=obsidian_config.get("note_filename_format", "{date} {title}.md"),
            )

            filepath = save_note(
                vault_path=obsidian_config["vault_path"],
                filename=filename,
                content=note_content,
            )

            # Only mark as processed after successful save
            state.mark_processed(message_id)
            created_count += 1
            logger.info("Successfully created note: %s", filepath)

        except Exception:
            logger.exception("Failed to process message %s", message_id)
            # Do NOT mark as processed — will be retried next run

    # Update poll timestamp
    state.update_poll_time()

    logger.info(
        "Run complete: %d note(s) created, %d skipped",
        created_count, skipped_count,
    )


if __name__ == "__main__":
    main()
