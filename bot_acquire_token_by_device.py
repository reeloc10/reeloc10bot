# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import json
import os
import sys
import time
import urllib.parse

import urllib_inspector
import bot

DEVICE_CODE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"

DEFAULT_SCOPE = "channel:read:redemptions"


def load_client_id() -> str:
    """Read token-specific configuration path from environment and extract twitch_client_id."""
    config_path = os.environ.get("BOT_TOKEN_CONFIG", "token_config.json")

    if not os.path.exists(config_path):
        print(f"[!] Token configuration file not found at: {config_path}. Using placeholder.")
        return "YOUR_CLIENT_ID"

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return raw.get("twitch_client_id", "YOUR_CLIENT_ID")
    except json.JSONDecodeError:
        print(f"[!] Failed to parse JSON config {config_path}", file=sys.stderr)
        sys.exit(1)

def main():
    client_id = load_client_id()
    scope = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCOPE

    print(f"[*] Requesting device code for Client ID: {client_id[:6]}... (Scope: {scope})")

    # 1. Request Device Code with the correct 'scopes' key
    device_data = urllib.parse.parse_qsl(urllib.parse.urlencode({
        "client_id": client_id,
        "scopes": scope  # <-- Changed from 'scope' to 'scopes'
    }))
    device_data_items = [f"{k}={v}" for k, v in device_data]

    # 1. Request Device Code via POST form items
    res = urllib_inspector.inspect_url(
        DEVICE_CODE_URL,
        follow_redirects=False,
        data_items=device_data_items
    )

    if not res["success"] or res["status_code"] != 200:
        print(f"[!] Failed to initiate device flow ({res.get('status_code')}): {res.get('body')}")
        sys.exit(1)

    try:
        res_data = json.loads(res["body"])
    except json.JSONDecodeError:
        print(f"[!] Failed to parse device code JSON response: {res['body']}")
        sys.exit(1)

    device_code = res_data.get("device_code")
    user_code = res_data.get("user_code")
    verification_uri = res_data.get("verification_uri")
    interval = res_data.get("interval", 5)
    expires_in = res_data.get("expires_in", 900)

    # 2. Instruct user
    print("\n" + "=" * 60)
    print(f"1. Open your browser and go to: {verification_uri}")
    print(f"2. Enter this User Code:           {user_code}")
    print(f"3. Authorize the application as your broadcaster account.")
    print("=" * 60 + "\n")
    print(f"[*] Waiting for authorization (expires in {expires_in}s)...")

    # 3. Poll for Token
    start_time = time.time()
    while time.time() - start_time < expires_in:
        time.sleep(interval)

        token_data = urllib.parse.parse_qsl(urllib.parse.urlencode({
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
        }))
        token_data_items = [f"{k}={v}" for k, v in token_data]

        token_res = urllib_inspector.inspect_url(
            TOKEN_URL,
            follow_redirects=False,
            data_items=token_data_items
        )

        if token_res["success"] and token_res["status_code"] == 200:
            try:
                t_data = json.loads(token_res["body"])
                access_token = t_data.get("access_token")
                refresh_token = t_data.get("refresh_token")

                if access_token:
                    print("\n[+] Token generated successfully!\n")

                    # Validate the newly generated access token using bot.py's validation function
                    print("[*] Validating newly acquired access token against Twitch...")
                    validation_info = bot.token_pipeline.validate_user_token(access_token, "Acquired Broadcaster Token")

                    print(f"\nAccess Token: {access_token}")
                    if refresh_token:
                        print(f"Refresh Token: {refresh_token}")
                    return
            except json.JSONDecodeError:
                pass
        else:
            try:
                err_json = json.loads(token_res["body"])
                err_msg = err_json.get("message", "")
                if err_msg == "authorization_pending":
                    print(".", end="", flush=True)
                    continue
                elif err_msg == "slow_down":
                    interval += 5
                    print("s", end="", flush=True)
                    continue
                else:
                    print(f"\n[!] Authorization error: {err_msg}")
                    sys.exit(1)
            except json.JSONDecodeError:
                pass

    print("\n[!] Device code expired before authorization was completed.")
    sys.exit(1)


if __name__ == "__main__":
    main()
