# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import asyncio
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

try:
    import websockets
except ModuleNotFoundError:
    print(f"\n{YELLOW}[*]{RESET} Missing websockets dependency.")

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TWITCH_WS_URL = "wss://eventsub.wss.twitch.tv/ws"


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


async def run_eventsub_listener(access_token: str, client_id: str):
    """Connect to Twitch EventSub WebSocket and handle incoming messages."""
    print(f"{CYAN}[*]{RESET} Connecting to EventSub WebSocket endpoint...")

    async with websockets.connect(TWITCH_WS_URL) as websocket:
        print(f"{GREEN}[+]{RESET} Connected to Twitch EventSub WebSocket.")

        async for raw_message in websocket:
            message = json.loads(raw_message)
            metadata = message.get("metadata", {})
            msg_type = metadata.get("message_type")

            if msg_type == "session_welcome":
                session_id = message["payload"]["session"]["id"]
                keepalive = message["payload"]["session"]["keepalive_timeout_seconds"]
                print(f"{GREEN}[+] Session established:{RESET} {BOLD}{session_id}{RESET} (Keepalive: {keepalive}s)")

                # TODO: Use urllib_inspector here to register your EventSub subscriptions
                # via POST /helix/eventsub/subscriptions using this session_id and access_token.

            elif msg_type == "session_keepalive":
                # Connection heartbeat; silent pass
                pass

            elif msg_type == "notification":
                sub_type = metadata.get("subscription_type")
                event_data = message["payload"]["event"]
                print(f"{CYAN}[EVENT]{RESET} Received {BOLD}{sub_type}{RESET}: {event_data}")

            elif msg_type == "session_reconnect":
                reconnect_url = message["payload"]["session"]["reconnect_url"]
                print(f"{YELLOW}[!] Reconnect requested to:{RESET} {reconnect_url}")
                break


def main():
    client_id = os.environ.get("TWITCH_CLIENT_ID", "placeholder_client_id")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "placeholder_client_secret")

    print(f"{CYAN}[*]{RESET} Initializing {BOLD}reeloc10bot{RESET}...")
    token_data = request_app_token(client_id, client_secret)

    if "access_token" in token_data:
        access_token = token_data["access_token"]
        expires = token_data.get('expires_in')
        print(f"{GREEN}[+]{RESET} Successfully obtained token! Expires in: {YELLOW}{expires}s{RESET}")

        # Hand off control to the async EventSub loop
        try:
            asyncio.run(run_eventsub_listener(access_token, client_id))
        except KeyboardInterrupt:
            print(f"\n{YELLOW}[*]{RESET} Bot stopped by user.")
    else:
        print(f"{YELLOW}[!] Bot initialization completed with mock/error token response. Skipping WebSocket listener.{RESET}", file=sys.stderr)


if __name__ == "__main__":
    main()
