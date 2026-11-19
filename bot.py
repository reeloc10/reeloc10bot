# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import asyncio
import dataclasses
import functools
import json
import os
import signal
import sys
import urllib.error

import urllib_inspector
import token_pipeline
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

SUBS_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"
CHAT_SEND_URL = "https://api.twitch.tv/helix/chat/messages"
TWITCH_WS_URL = "wss://eventsub.wss.twitch.tv/ws"

# WebSocket Keepalive Tuning
WS_PING_INTERVAL = 30
WS_PING_TIMEOUT = 30


class StreamSession:
    def __init__(self):
        self.reset_session()

    def reset_session(self):
        self.is_live = False
        self.session_visitors = set()          # Unique users who messaged or redeemed this stream
        self.daily_redeems_count = 0          # Total check-ins for current stream
        self.followers_this_stream = 0        # New followers since stream started


session = StreamSession()


def abbreviate_token(token: str) -> str:
    """Safely abbreviate a token for debug output."""
    if not token:
        return "EMPTY"
    return f"{token[:3]}... (Length: {len(token)})" if len(token) > 3 else "EMPTY"


def early_sigint_handler(sig, frame):
    """Simple handler for early initialization phase."""
    print(f"\n{YELLOW}[*]{RESET} Aborted during initialization. Exiting...")
    sys.exit(0)


def handle_sigint(sig, frame, client_id, app_token, broadcaster_id, bot_id):
    """Intercept Ctrl+C, send shutdown message to chat, and exit cleanly."""
    print(f"\n{YELLOW}[*]{RESET} Shutting down reeloc10bot...")

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
    """Read configuration path from environment and parse JSON config into raw dict."""
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


def subscribe_eventsub_topics(client_id: str, sub_token: str, session_id: str, broadcaster_id: str, bot_id: str, is_broadcaster_token: bool = False) -> int:
    """
    Subscribe to EventSub topics appropriate for the given session identity.
    Uses app_token for bot chat subscriptions and broadcaster token for broadcaster topics.
    """
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {sub_token}",
        "Content-Type": "application/json"
    }

    if is_broadcaster_token:
        subscriptions = [
            {
                "type": "stream.online",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                },
                "optional": False
            },
            {
                "type": "channel.channel_points_custom_reward_redemption.add",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                },
                "optional": False
            }
        ]
    else:
        subscriptions = [
            {
                "type": "channel.chat.message",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id,
                    "user_id": bot_id
                },
                "optional": False
            },
            {
                "type": "channel.follow",
                "version": "2",
                "condition": {
                    "broadcaster_user_id": broadcaster_id,
                    "moderator_user_id": bot_id
                },
                "optional": True
            },
            {
                "type": "stream.online",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                },
                "optional": True
            },
            {
                "type": "stream.offline",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": broadcaster_id
                },
                "optional": True
            }
        ]

    active_subs_count = 0
    token_tag = "Broadcaster" if is_broadcaster_token else "Bot"

    for sub in subscriptions:
        payload = {
            "type": sub["type"],
            "version": sub["version"],
            "condition": sub["condition"],
            "transport": {
                "method": "websocket",
                "session_id": session_id
            }
        }

        token_repr = abbreviate_token(sub_token)
        print(f"{GRAY}[DEBUG] [{token_tag}] Subscribing to {sub['type']} using token: {token_repr}{RESET}", file=sys.stderr)

        res = urllib_inspector.inspect_url(
            SUBS_URL,
            custom_headers=headers,
            raw_json=json.dumps(payload)
        )

        sub_type = sub["type"]
        is_optional = sub.get("optional", False)
        status = res.get("status_code")
        body = res.get("body")
        if isinstance(body, bytes):
            body = body.decode("utf-8")

        print(f"{GRAY}[DEBUG] [{token_tag}] {sub_type} -> Status: {status}, Body: {body}{RESET}", file=sys.stderr)

        if res["success"] and status in (200, 202):
            print(f"{GREEN}[+]{RESET} [{token_tag}] Subscribed to {BOLD}{sub_type}{RESET}!")
            active_subs_count += 1
        elif status in (401, 403) and is_optional:
            print(f"{YELLOW}[!] [{token_tag}] Optional subscription skipped ({sub_type}) due to missing scope/auth ({status}).{RESET}")
        else:
            print(f"{RED}[!] [{token_tag}] Failed subscription for {sub_type} ({status}): {body}{RESET}", file=sys.stderr)
            if not is_optional:
                print(f"{RED}[!] Mandatory subscription {sub_type} failed!{RESET}", file=sys.stderr)

    return active_subs_count


def send_chat_message(
    client_id: str,
    token: str,
    broadcaster_id: str,
    bot_id: str,
    message: str,
    reply_parent_message_id: str | None = None
) -> bool:
    """Send a chat message via Twitch Helix API using App or User Access Token."""
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

    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if res["success"] and res["status_code"] == 200:
        try:
            data = json.loads(body)
            chat_data = data.get("data", [])
            if chat_data and chat_data[0].get("is_sent") is False:
                print(f"{RED}[!] Message blocked or dropped by Twitch chat rules: {body}{RESET}", file=sys.stderr)
                return False
            return True
        except json.JSONDecodeError:
            return True
    else:
        print(f"{RED}[!] Failed to send chat message ({res['status_code']}): {body}{RESET}", file=sys.stderr)
        return False


async def run_eventsub_session(
    ws_url: str,
    ws_token: str,
    app_token: str,
    client_id: str,
    broadcaster_id: str,
    bot_id: str,
    is_broadcaster_token: bool = False,
    is_reconnect: bool = False
) -> str | None:
    """Run a single EventSub WebSocket session for either Bot or Broadcaster."""
    global session
    label = "Broadcaster" if is_broadcaster_token else "Bot"
    print(f"{CYAN}[*]{RESET} [{label}] Connecting to EventSub WebSocket endpoint...")

    async with websockets.connect(
        ws_url,
        ping_interval=WS_PING_INTERVAL,
        ping_timeout=WS_PING_TIMEOUT
    ) as websocket:
        print(f"{GREEN}[+]{RESET} [{label}] Connected to Twitch EventSub WebSocket.")

        greeting_sent = False

        async for raw_message in websocket:
            message = json.loads(raw_message)
            metadata = message.get("metadata", {})
            msg_type = metadata.get("message_type")

            if msg_type == "session_welcome":
                session_id = message["payload"]["session"]["id"]
                keepalive = message["payload"]["session"]["keepalive_timeout_seconds"]
                print(f"{GREEN}[+] [{label}] Session established:{RESET} {BOLD}{session_id}{RESET} (Keepalive: {keepalive}s)")
                if not is_reconnect:
                    print(f"[*] [{label}] Token fingerprint: {abbreviate_token(ws_token)}")

                    subscription_token = ws_token

                    subs_succeeded = await asyncio.to_thread(
                        subscribe_eventsub_topics,
                        client_id,
                        subscription_token,
                        session_id,
                        broadcaster_id,
                        bot_id,
                        is_broadcaster_token
                    )

                    if subs_succeeded == 0:
                        print(f"{RED}[!] [{label}] Zero active subscriptions registered. Closing thread cleanly.{RESET}")
                        return None

                    if is_broadcaster_token and not greeting_sent:
                        greeting_sent = True
                        print(f"{GREEN}[->]{RESET} Sending startup greeting to chat...")
                        try:
                            await asyncio.wait_for(
                                asyncio.to_thread(
                                    send_chat_message,
                                    client_id,
                                    app_token,
                                    broadcaster_id,
                                    bot_id,
                                    "Hello chat"
                                ),
                                timeout=5.0
                            )
                            print(f"{GREEN}[+] Startup greeting sent successfully via App Token.{RESET}")
                        except asyncio.TimeoutError:
                            print(f"{RED}[!] Startup greeting timed out (API endpoint unresponsive).{RESET}", file=sys.stderr)
                        except Exception as e:
                            print(f"{RED}[!] Startup greeting error: {e}{RESET}", file=sys.stderr)

            elif msg_type == "session_keepalive":
                pass

            elif msg_type == "notification":
                sub_type = metadata.get("subscription_type")
                event_data = message["payload"]["event"]
                print(f"{CYAN}[EVENT:{label}]{RESET} Received {BOLD}{sub_type}{RESET}")

                if sub_type == "stream.online":
                    session.reset_session()
                    session.is_live = True
                    print(f"{GREEN}[*] Stream went LIVE. Session stats reset.{RESET}")

                elif sub_type == "stream.offline":
                    session.is_live = False
                    print(f"\n{YELLOW}=== STREAM OFFLINE - SESSION SUMMARY ==={RESET}")
                    print(f"• Unique Visitors (Chat / Check-in): {len(session.session_visitors)}")
                    print(f"• 'Daily check' Redemptions: {session.daily_redeems_count}")
                    print(f"• New Followers This Stream: {session.followers_this_stream}")
                    print(f"{YELLOW}========================================={RESET}\n")
                    session.reset_session()

                elif sub_type == "channel.follow":
                    session.followers_this_stream += 1
                    username = event_data.get("user_name")
                    print(f"{GREEN}[+] New follower this stream:{RESET} {BOLD}{username}{RESET}")

                elif sub_type == "channel.channel_points_custom_reward_redemption.add":
                    reward_title = event_data.get("reward", {}).get("title", "")
                    if reward_title == "Daily check":
                        session.daily_redeems_count += 1
                        username = event_data.get("user_name")
                        session.session_visitors.add(username)

                        log_msg = f"Daily check redeem: {username} (Total today: {session.daily_redeems_count})"
                        print(f"{GREEN}[+]{RESET} {log_msg}")

                        await asyncio.to_thread(
                            send_chat_message,
                            client_id,
                            app_token,
                            broadcaster_id,
                            bot_id,
                            log_msg
                        )

                elif sub_type == "channel.chat.message":
                    chatter_id = event_data.get("chatter_user_id")
                    chatter = event_data.get("chatter_user_name")
                    message_id = event_data.get("message_id")
                    text = event_data.get("message", {}).get("text", "").strip()
                    print(f"{CYAN}[CHAT]{RESET} {BOLD}{chatter}{RESET}: {text}")

                    if chatter_id == bot_id:
                        continue

                    if chatter not in session.session_visitors:
                        session.session_visitors.add(chatter)
                        welcome_msg = f"Hi @{chatter}!"
                        await asyncio.to_thread(
                            send_chat_message,
                            client_id,
                            app_token,
                            broadcaster_id,
                            bot_id,
                            welcome_msg,
                            message_id
                        )
                        print(f"{GREEN}[->]{RESET} Welcomed new session chatter {BOLD}{chatter}{RESET}")

                    reply_text = bot_responses.evaluate_message(text, chatter)
                    if reply_text:
                        print(f"[*] Effective write token fingerprint: {abbreviate_token(app_token)}")
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

            elif msg_type == "session_reconnect":
                reconnect_url = message["payload"]["session"]["reconnect_url"]
                print(f"{YELLOW}[!] [{label}] Reconnect requested to:{RESET} {reconnect_url}")
                return reconnect_url

    return None


async def supervise_listener(ws_token: str, app_token: str, client_id: str, broadcaster_id: str, bot_id: str, is_broadcaster_token: bool = False):
    """Supervise an EventSub WebSocket session across reconnects and network drops."""
    next_url = TWITCH_WS_URL
    is_reconnect = False
    label = "Broadcaster" if is_broadcaster_token else "Bot"

    while True:
        try:
            reconnect_url = await run_eventsub_session(
                next_url,
                ws_token,
                app_token,
                client_id,
                broadcaster_id,
                bot_id,
                is_broadcaster_token=is_broadcaster_token,
                is_reconnect=is_reconnect
            )
            if reconnect_url:
                next_url = reconnect_url
                is_reconnect = True
            else:
                print(f"{YELLOW}[*] [{label}] Thread closed cleanly (no reconnect requested).{RESET}")
                break
        except websockets.exceptions.ConnectionClosed as e:
            print(f"{YELLOW}[!] [{label}] WebSocket closed ({e.code}: {e.reason}). Reconnecting in 3s...{RESET}", file=sys.stderr)
            next_url = TWITCH_WS_URL
            is_reconnect = False
            await asyncio.sleep(3)
        except (
            websockets.exceptions.WebSocketException,
            OSError,
            TimeoutError,
            json.JSONDecodeError,
        ) as e:
            print(f"{RED}[!] [{label}] Transient listener error: {e}. Reconnecting in 5s...{RESET}", file=sys.stderr)
            next_url = TWITCH_WS_URL
            is_reconnect = False
            await asyncio.sleep(5)


def main():
    signal.signal(signal.SIGINT, early_sigint_handler)

    config = load_config()
    client_id = config.get("twitch_client_id", "")
    client_secret = config.get("twitch_client_secret", "")

    if not client_id or not client_secret:
        print(f"{RED}[!] Missing 'twitch_client_id' or 'twitch_client_secret' in configuration file.{RESET}", file=sys.stderr)
        sys.exit(1)

    print(f"{CYAN}[*]{RESET} Initializing {BOLD}reeloc10bot{RESET}...")

    try:
        app_token_data = token_pipeline.mint_app_token(client_id, client_secret)
        app_token = app_token_data["access_token"]
        print(f"{GREEN}[+]{RESET} Obtained App Token (expires in {YELLOW}{app_token_data.get('expires_in')}s{RESET})")

        active_tokens, resolved_ids = token_pipeline.resolve_token_pipeline(config, app_token)
    except Exception as e:
        print(f"{RED}[!] Initialization failed: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    broadcaster_id = resolved_ids["broadcaster"]
    bot_id = resolved_ids["bot"]

    bot_entry = active_tokens.get("bot")
    broadcaster_entry = active_tokens.get("broadcaster")

    running_sigint_handler = functools.partial(
        handle_sigint,
        client_id=client_id,
        app_token=app_token,
        broadcaster_id=broadcaster_id,
        bot_id=bot_id
    )
    signal.signal(signal.SIGINT, running_sigint_handler)

    async def main_loop():
        tasks = []
        if bot_entry:
            tasks.append(
                supervise_listener(bot_entry["access_token"], app_token, client_id, broadcaster_id, bot_id, is_broadcaster_token=False)
            )
        if broadcaster_entry:
            tasks.append(
                supervise_listener(broadcaster_entry["access_token"], app_token, client_id, broadcaster_id, bot_id, is_broadcaster_token=True)
            )
        if not tasks:
            print(f"{RED}[!] Error: No active token entries configured for listeners!{RESET}", file=sys.stderr)
            sys.exit(1)

        await asyncio.gather(*tasks)

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[*]{RESET} Bot stopped by user.")

    print(f"\n{YELLOW}[*]{RESET} reeloc10bot shutdown complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()
