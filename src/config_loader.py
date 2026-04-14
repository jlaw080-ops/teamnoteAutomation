import logging
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "gmail": {
        "credentials_path": "credentials/credentials.json",
        "token_path": "credentials/token.json",
        "sender_filter": "team@genspark.ai",
        "subject_prefix": "Meeting Notes:",
    },
    "obsidian": {
        "vault_path": "",
        "template_path": "",
        "note_filename_format": "{date} {title}.md",
    },
    "polling": {
        "lookback_hours": 24,
        "max_results": 10,
    },
    "state": {
        "state_file": "state.json",
        "max_tracked_ids": 500,
    },
    "logging": {
        "level": "INFO",
        "log_file": "logs/automation.log",
    },
}


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        logger.error("Copy config.example.yaml to config.yaml and update your settings.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}

    config = _merge_config(DEFAULT_CONFIG, user_config)
    _validate_config(config)
    return config


def _merge_config(defaults: dict, overrides: dict) -> dict:
    merged = {}
    for key, default_val in defaults.items():
        if key in overrides:
            if isinstance(default_val, dict) and isinstance(overrides[key], dict):
                merged[key] = _merge_config(default_val, overrides[key])
            else:
                merged[key] = overrides[key]
        else:
            merged[key] = default_val
    for key in overrides:
        if key not in defaults:
            merged[key] = overrides[key]
    return merged


def _validate_config(config: dict):
    vault_path = config["obsidian"].get("vault_path", "")
    if not vault_path:
        logger.error("obsidian.vault_path is required in config.yaml")
        sys.exit(1)

    template_path = config["obsidian"].get("template_path", "")
    if not template_path:
        logger.error("obsidian.template_path is required in config.yaml")
        sys.exit(1)

    credentials_path = config["gmail"].get("credentials_path", "")
    if not credentials_path:
        logger.error("gmail.credentials_path is required in config.yaml")
        sys.exit(1)
