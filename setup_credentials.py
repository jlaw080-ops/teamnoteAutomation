#!/usr/bin/env python3
"""One-time OAuth2 setup helper.

Run this script once on your Windows machine to complete the browser-based
OAuth flow. After successful authentication, a token.json file will be saved
and subsequent runs of main.py will use the stored refresh token.

Usage:
    python setup_credentials.py [--config config.yaml]
"""

import argparse
import sys

from src.config_loader import load_config
from src.gmail_client import GmailClient


def main():
    parser = argparse.ArgumentParser(description="Gmail OAuth2 credential setup")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    print("=" * 50)
    print("Gmail OAuth2 Credential Setup")
    print("=" * 50)
    print()
    print("A browser window will open for Google authentication.")
    print("Sign in with the Gmail account that receives meeting notes.")
    print()

    client = GmailClient(
        credentials_path=config["gmail"]["credentials_path"],
        token_path=config["gmail"]["token_path"],
    )

    try:
        client.authenticate()
        print()
        print("Authentication successful!")
        print(f"Token saved to: {config['gmail']['token_path']}")
        print()
        print("You can now run main.py to start processing meeting notes.")
    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nAuthentication failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
