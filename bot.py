# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import asyncio
import functools
import json
import os
import signal
import sys
import urllib.error

import urllib_inspector

import bot_responses

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
    print(f"\n{YELLOW}[*]{RESET} Missing websockets dependency. EventSub listener will be unavailable.")

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
USERS_URL = "https://api.twitch.tv/helix/users"
SUBS_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"
CHAT_SEND_URL = "https://api.twitch.tv/helix/chat/messages"
TWITCH_WS_URL = "wss://eventsub.wss.twitch.tv/ws"

# WebSocket Keepalive Tuning (websockets library defaults: ping_interval=20, ping_timeout=20)
WS_PING_INTERVAL = 30
WS_PING_TIMEOUT = 30


def early_sigint_handler(sig, frame):
    """Simple handler for early initialization phase (no chat message possible yet)."""
    print(f"\n{YELLOW}[*]{RESET} Aborted during initialization. Exiting...")
    sys.exit(0)


def handle_sigint(sig, frame, client_id, app_token, broadcaster_id, bot_id):
    """Intercept Ctrl+C, send shutdown message to chat, and exit cleanly."""
    print(f"\n{YELLOW}[*]{RESET} Shutting down reeloc10bot...")

    # Send final shutdown message to Twitch chat
    try:
        send_chat_message(
            client_id=client_id,
            token=app_token,
            broadcaster_id=broadcaster_id,
            bot_id=bot_id,
            message="Shutting down. Farewell!"
        )
        print(f"{GREEN}[->]{RESET} Shutdown notice sent to chat.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"{RED}[!] Failed to send shutdown message due to network error: {e}{RESET}", file=sys.stderr)

    print(f"\n{YELLOW}[*]{RESET} Bot offline.")
    sys.exit(0)


def load_config() -> dict:
    """Read configuration path from environment and parse JSON config directly."""
    config_path = os.environ.get("BOT_CONFIG", "config.json")

    if not os.path.exists(config_path):
        print(f"{RED}[!] Configuration file not found at: {config_path}{RESET}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"{RED}[!] Failed to parse JSON config {config_path}: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def validate_user_token(token: str) -> dict:
    """Validate user access token using Twitch /oauth2/validate endpoint via urllib_inspector."""
    headers = [
        f"Authorization: OAuth {token}"
    ]

    res = urllib_inspector.inspect_url(
        VALIDATE_URL,
        custom_headers=headers
    )

    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if res["success"] and res["status_code"] == 200:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    else:
        print(f"{RED}[!] Token validation failed ({res['status_code']}): {body}{RESET}", file=sys.stderr)
        return {}


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


def get_user_id(client_id: str, token: str, login: str) -> str:
    """Fetch Twitch User ID for a given login name using urllib_inspector."""
    url = f"{USERS_URL}?login={login}"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}"
    }

    res = urllib_inspector.inspect_url(
        url,
        custom_headers=headers
    )
    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if res["success"] and res["status_code"] == 200:
        data = json.loads(res["body"]).get("data", [])
        if data:
            return data[0]["id"]
    print(f"{RED}[!] Failed to resolve user ID for {login} ({res['status_code']}): {res['body']}{RESET}", file=sys.stderr)
    return ""


def subscribe_chat_message(client_id: str, token: str, session_id: str, broadcaster_id: str, bot_id: str) -> bool:
    """Subscribe to chat messages using EventSub WebSocket session. Returns True on success."""
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "type": "channel.chat.message",
        "version": "1",
        "condition": {
            "broadcaster_user_id": broadcaster_id,
            "user_id": bot_id
        },
        "transport": {
            "method": "websocket",
            "session_id": session_id
        }
    }

    res = urllib_inspector.inspect_url(
        SUBS_URL,
        custom_headers=headers,
        raw_json=json.dumps(payload)
    )

    if res["success"] and res["status_code"] in (200, 202):
        print(f"{GREEN}[+]{RESET} Subscribed to {BOLD}channel.chat.message{RESET}!")
        return True
    else:
        print(f"{RED}[!] EventSub subscription failed ({res['status_code']}): {res['body']}{RESET}", file=sys.stderr)
        return False


def send_chat_message(
    client_id: str,
    token: str,
    broadcaster_id: str,
    bot_id: str,
    message: str,
    reply_parent_message_id: str | None = None
) -> bool:
    """Send a chat message via Twitch Helix API using urllib_inspector."""
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "broadcaster_id": broadcaster_id,
        "sender_id": bot_id,
        "message": message[:500]
    }
    if reply_parent_message_id:
        payload["reply_parent_message_id"] = reply_parent_message_id

    res = urllib_inspector.inspect_url(
        CHAT_SEND_URL,
        custom_headers=headers,
        raw_json=json.dumps(payload)
    )

    if res["success"] and res["status_code"] == 200:
        return True
    else:
        print(f"{RED}[!] Failed to send chat message ({res['status_code']}): {res['body']}{RESET}", file=sys.stderr)
        return False


async def run_eventsub_session(
    ws_url: str,
    ws_token: str,
    app_token: str,
    client_id: str,
    broadcaster_id: str,
    bot_id: str,
    is_reconnect: bool = False
) -> str | None:
    """Run a single EventSub WebSocket session. Returns a reconnect_url if requested, else None."""
    print(f"{CYAN}[*]{RESET} Connecting to EventSub WebSocket endpoint...")

    async with websockets.connect(
        ws_url,
        ping_interval=WS_PING_INTERVAL,
        ping_timeout=WS_PING_TIMEOUT
    ) as websocket:
        print(f"{GREEN}[+]{RESET} Connected to Twitch EventSub WebSocket.")

        async for raw_message in websocket:
            message = json.loads(raw_message)
            metadata = message.get("metadata", {})
            msg_type = metadata.get("message_type")

            if msg_type == "session_welcome":
                session_id = message["payload"]["session"]["id"]
                keepalive = message["payload"]["session"]["keepalive_timeout_seconds"]
                print(f"{GREEN}[+] Session established:{RESET} {BOLD}{session_id}{RESET} (Keepalive: {keepalive}s)")
                if not is_reconnect:
                    print(f"[*] Effective token fingerprint: {ws_token[:3]}... (Length: {len(ws_token)})")
                    await asyncio.to_thread(
                        subscribe_chat_message,
                        client_id,
                        ws_token,
                        session_id,
                        broadcaster_id,
                        bot_id
                    )

            elif msg_type == "session_keepalive":
                pass

            elif msg_type == "notification":
                sub_type = metadata.get("subscription_type")
                event_data = message["payload"]["event"]
                if sub_type == "channel.chat.message":
                    chatter_id = event_data.get("chatter_user_id")
                    chatter = event_data.get("chatter_user_name")
                    message_id = event_data.get("message_id")
                    text = event_data.get("message", {}).get("text", "").strip()
                    print(f"{CYAN}[CHAT]{RESET} {BOLD}{chatter}{RESET}: {text}")

                    # Guard against self-replies
                    if chatter_id == bot_id:
                        continue

                    # Evaluate incoming text against standalone bot_responses module
                    reply_text = bot_responses.evaluate_message(text, chatter)
                    if reply_text:
                        print(f"[*] Effective write token fingerprint: {app_token[:3]}... (Length: {len(app_token)})")
                        sent = await asyncio.to_thread(
                            send_chat_message,
                            client_id,
                            app_token,
                            broadcaster_id,
                            bot_id,
                            reply_text,
                            message_id
                        )
                        if sent:
                            print(f"{GREEN}[->]{RESET} Replied to {BOLD}{chatter}{RESET}: {reply_text}")
                else:
                    print(f"{CYAN}[EVENT]{RESET} Received {BOLD}{sub_type}{RESET}: {event_data}")

            elif msg_type == "session_reconnect":
                reconnect_url = message["payload"]["session"]["reconnect_url"]
                print(f"{YELLOW}[!] Reconnect requested to:{RESET} {reconnect_url}")
                return reconnect_url

    return None


async def run_eventsub_listener(ws_token: str, app_token: str, client_id: str, broadcaster_id: str, bot_id: str):
    """Supervise EventSub WebSocket sessions across reconnects and transient network drops."""
    next_url = TWITCH_WS_URL
    is_reconnect = False

    while True:
        try:
            reconnect_url = await run_eventsub_session(
                next_url,
                ws_token,
                app_token,
                client_id,
                broadcaster_id,
                bot_id,
                is_reconnect=is_reconnect
            )
            if reconnect_url:
                next_url = reconnect_url
                is_reconnect = True
            else:
                next_url = TWITCH_WS_URL
                is_reconnect = False
                await asyncio.sleep(3)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"{YELLOW}[!] WebSocket closed ({e.code}: {e.reason}). Reconnecting in 3s...{RESET}")
            next_url = TWITCH_WS_URL
            is_reconnect = False
            await asyncio.sleep(3)
        except (
            websockets.exceptions.WebSocketException,
            OSError,
            TimeoutError,
            json.JSONDecodeError,
        ) as e:
            print(f"{RED}[!] Transient listener error: {e}. Reconnecting in 5s...{RESET}", file=sys.stderr)
            next_url = TWITCH_WS_URL
            is_reconnect = False
            await asyncio.sleep(5)


def main():
    # 1. Register early safety handler right at boot
    signal.signal(signal.SIGINT, early_sigint_handler)

    config = load_config()
    client_id = config.get("twitch_client_id")
    client_secret = config.get("twitch_client_secret")
    broadcaster_login = config.get("broadcaster_login", "reeloc10")
    bot_login = config.get("bot_login", "reeloc10bot")
    user_token = config.get("twitch_user_token")

    if not client_id or not client_secret:
        print(f"{RED}[!] Missing 'twitch_client_id' or 'twitch_client_secret' in configuration file.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{CYAN}[*]{RESET} Initializing {BOLD}reeloc10bot{RESET}...")

    if not user_token:
        print(f"{RED}[!] Error: 'twitch_user_token' is missing from your configuration file!{RESET}", file=sys.stderr)
        print(f"{RED}[!] App Access Tokens cannot be used for user-bound chat event subscriptions.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{GREEN}[+]{RESET} Loaded User Access Token from configuration.")
    print(f"[*] Token fingerprint: {user_token[:6]}...{user_token[-4:]} (Length: {len(user_token)})")

    # Validate the acquired user token against Twitch
    print(f"{CYAN}[*]{RESET} Validating User Access Token with Twitch...")
    token_info = validate_user_token(user_token)

    if token_info:
        client_id_full = token_info.get('client_id', '')
        client_id_abbr = f"{client_id_full[:6]}..." if len(client_id_full) > 6 else client_id_full

        print(f"{GREEN}[+]{RESET} Token validated successfully!")
        print(f"    - Client ID: {client_id_abbr}")
        print(f"    - Login: {token_info.get('login')}")
        print(f"    - User ID: {token_info.get('user_id')}")
        print(f"    - Scopes: {token_info.get('scopes')}")
    else:
        print(f"{RED}[!] Token validation failed or returned empty details. Proceeding with caution...{RESET}")

    token_data = request_app_token(client_id, client_secret)

    if "access_token" in token_data:
        app_token = token_data["access_token"]
        expires = token_data.get('expires_in')
        print(f"{GREEN}[+]{RESET} Successfully obtained App Token for API lookups! Expires in: {YELLOW}{expires}s{RESET}")

        broadcaster_id = get_user_id(client_id, app_token, broadcaster_login)
        bot_id = get_user_id(client_id, app_token, bot_login)
        print(f"{GRAY}[*] IDs -> Broadcaster ({broadcaster_login}): {broadcaster_id} | Bot ({bot_login}): {bot_id}{RESET}")

        # 2. Initialization passed! Swap to full shutdown handler with context bound.
        running_sigint_handler = functools.partial(
            handle_sigint,
            client_id=client_id,
            app_token=app_token,
            broadcaster_id=broadcaster_id,
            bot_id=bot_id
        )
        signal.signal(signal.SIGINT, running_sigint_handler)

        ws_token = user_token

        try:
            asyncio.run(run_eventsub_listener(ws_token, app_token, client_id, broadcaster_id, bot_id))
        except KeyboardInterrupt:
            print(f"\n{YELLOW}[*]{RESET} Bot stopped by user.")
    else:
        print(f"{YELLOW}[!] Bot initialization completed with mock/error token response. Skipping WebSocket listener.{RESET}", file=sys.stderr)

    early_sigint_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main()
