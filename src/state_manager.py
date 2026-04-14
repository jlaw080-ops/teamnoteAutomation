import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, state_file: str, max_tracked_ids: int = 500):
        self.state_file = Path(state_file)
        self.max_tracked_ids = max_tracked_ids
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logger.info("Loaded state: %d processed IDs", len(state.get("processed_ids", [])))
                return state
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load state file, starting fresh: %s", e)
        return {
            "last_poll_utc": None,
            "processed_ids": [],
        }

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self.state_file.parent, suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.state_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    @property
    def last_poll_utc(self) -> str | None:
        return self._state.get("last_poll_utc")

    def is_processed(self, message_id: str) -> bool:
        return message_id in self._state["processed_ids"]

    def mark_processed(self, message_id: str):
        if message_id not in self._state["processed_ids"]:
            self._state["processed_ids"].append(message_id)
            if len(self._state["processed_ids"]) > self.max_tracked_ids:
                excess = len(self._state["processed_ids"]) - self.max_tracked_ids
                self._state["processed_ids"] = self._state["processed_ids"][excess:]
            self._save()
            logger.debug("Marked message %s as processed", message_id)

    def update_poll_time(self):
        self._state["last_poll_utc"] = datetime.now(timezone.utc).isoformat()
        self._save()
