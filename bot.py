# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import json
import os
import sys

import urllib_inspector

# ANSI Color Constants
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
GRAY = "\033[90m"

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"


def request_app_token(client_id: str, client_secret: str) -> dict:
    """Request an App Access Token from Twitch using client credentials POST."""
    print(f"{CYAN}[*]{RESET} Requesting App Access Token for Client ID: {BOLD}{client_id[:6]}...{RESET}")
    
    res = urllib_inspector.inspect_url(
        TOKEN_URL,
        follow_redirects=False,
        data_items=[
            f"client_id={client_id}",
            f"client_secret={client_secret}",
            "grant_type=client_credentials"
        ]
    )
    
    if res["success"] and res["status_code"] == 200:
        return json.loads(res["body"])
    else:
        print(f"{RED}[!] Token request failed ({res['status_code']}): {res['body']}{RESET}", file=sys.stderr)
        return {}


def main():
    # Placeholder or environment fallback
    client_id = os.environ.get("TWITCH_CLIENT_ID", "placeholder_client_id")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "placeholder_client_secret")

    print(f"{CYAN}[*]{RESET} Initializing {BOLD}reeloc10bot{RESET}...")
    token_data = request_app_token(client_id, client_secret)

    if "access_token" in token_data:
        expires = token_data.get('expires_in')
        print(f"{GREEN}[+]{RESET} Successfully obtained token! Expires in: {YELLOW}{expires}s{RESET}")
    else:
        print(f"{YELLOW}[!] Bot initialization completed with mock/error token response.{RESET}", file=sys.stderr)


if __name__ == "__main__":
    main()
