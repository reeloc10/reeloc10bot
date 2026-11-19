# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import sys

import urllib_inspector

# Import load_config from bot.py to avoid duplication
from bot import load_config

# ANSI Color Constants
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
CYAN = "\033[36m"

REVOKE_URL = "https://id.twitch.tv/oauth2/revoke"


def main():
    config = load_config()
    client_id = config.client_id
    user_token = config.bot_token

    if not client_id or not user_token:
        print(f"{RED}[!] Missing 'twitch_client_id' or 'twitch_user_token' in configuration file.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{CYAN}[*]{RESET} Revoking User Access Token for Client ID: {BOLD}{client_id[:6]}...{RESET}")

    res = urllib_inspector.inspect_url(
        REVOKE_URL,
        follow_redirects=False,
        data_items=[
            f"client_id={client_id}",
            f"token={user_token}"
        ]
    )

    if res["success"] and res["status_code"] == 200:
        print(f"{GREEN}[+]{RESET} Token successfully and immediately revoked on Twitch!")
    else:
        body = res.get("body")
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        print(f"{RED}[!] Revocation failed ({res['status_code']}): {body}{RESET}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
