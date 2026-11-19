# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import json
import sys
import urllib_inspector

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
USERS_URL = "https://api.twitch.tv/helix/users"


def fetch_user_id(client_id: str, app_token: str, login: str) -> str:
    """Resolve a Twitch login name to its numeric user ID via /helix/users."""
    res = urllib_inspector.inspect_url(
        f"{USERS_URL}?login={login}",
        custom_headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {app_token}",
        },
    )
    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if res["success"] and res["status_code"] == 200:
        data = json.loads(body).get("data", [])
        if data:
            return data[0]["id"]
    raise RuntimeError(f"Failed to resolve user ID for '{login}' ({res.get('status_code')}): {body}")


def mint_app_token(client_id: str, client_secret: str) -> dict:
    """Mints an App Access Token via client_credentials."""
    res = urllib_inspector.inspect_url(
        TOKEN_URL,
        follow_redirects=False,
        data_items=[
            f"client_id={client_id}",
            f"client_secret={client_secret}",
            "grant_type=client_credentials",
        ],
    )
    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if not res["success"] or res["status_code"] != 200:
        raise RuntimeError(f"App token mint failed ({res.get('status_code')}): {body}")
    return json.loads(body)


def refresh_user_token(client_id: str, client_secret: str, refresh_token: str) -> dict | None:
    """Refreshes a User Access Token when flow == 'user'."""
    res = urllib_inspector.inspect_url(
        TOKEN_URL,
        follow_redirects=False,
        data_items=[
            f"client_id={client_id}",
            f"client_secret={client_secret}",
            "grant_type=refresh_token",
            f"refresh_token={refresh_token}",
        ],
    )
    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if not res["success"] or res["status_code"] != 200:
        return None
    return json.loads(body)


def validate_user_token(token: str, token_label: str) -> dict | None:
    """Validate a user access token using Twitch /oauth2/validate and print detailed info."""
    fingerprint = f"{token[:3]}... (Length: {len(token)})" if len(token) > 3 else "EMPTY"
    print(f"\033[36m[*]\033[0m Validating {token_label} Access Token [Fingerprint: {fingerprint}]...")

    res = urllib_inspector.inspect_url(
        VALIDATE_URL,
        follow_redirects=False,
        custom_headers=[f"Authorization: OAuth {token}"],
    )
    body = res.get("body")
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    if res["success"] and res["status_code"] == 200:
        try:
            info = json.loads(body)
            client_id_full = info.get('client_id', '')
            client_id_abbr = f"{client_id_full[:6]}..." if len(client_id_full) > 6 else "EMPTY"

            print(f"\033[32m[+]\033[0m {token_label} validated successfully!")
            print(f"    - Client ID: {client_id_abbr}")
            print(f"    - Login: {info.get('login')}")
            print(f"    - User ID: {info.get('user_id')}")
            print(f"    - Scopes: {info.get('scopes')}")
            return info
        except json.JSONDecodeError:
            return {}
    else:
        print(f"\033[31m[!]\033[0m {token_label} validation failed ({res['status_code']}): {body}", file=sys.stderr)
        return None


def resolve_token_pipeline(config: dict, app_token: str) -> tuple[dict, dict]:
    """
    Resolves broadcaster_login and bot_login to numeric IDs via /helix/users,
    then activates enabled entries in config['tokens'] one by one.
    Returns (active_tokens_by_role, resolved_ids).
    """
    client_id = config["twitch_client_id"]
    client_secret = config.get("twitch_client_secret", "")
    broadcaster_login = config.get("broadcaster_login", "reeloc10")
    bot_login = config.get("bot_login", "reeloc10bot")

    resolved_ids = {
        "broadcaster": fetch_user_id(client_id, app_token, broadcaster_login),
        "bot": fetch_user_id(client_id, app_token, bot_login),
    }
    print(f"[*] Resolved IDs -> broadcaster ({broadcaster_login}): {resolved_ids['broadcaster']} | bot ({bot_login}): {resolved_ids['bot']}")

    active_tokens = {}

    for idx, entry in enumerate(config.get("tokens", []), start=1):
        name = entry.get("name", f"token_{idx}")
        if not entry.get("enabled", True):
            print(f"[-] Skipping disabled token [{idx}]: {name}")
            continue

        flow = entry.get("flow")
        role = entry.get("role", f"role_{idx}")
        target = entry.get("target")
        if target not in resolved_ids:
            raise ValueError(f"Token '{name}' has invalid target '{target}': expected 'broadcaster' or 'bot'.")
        target_id = resolved_ids[target]

        print(f"[*] Activating [{idx}] {name} (flow={flow}, role={role}, target={target})...")

        if flow == "app":
            active_tokens[role] = {
                "access_token": app_token,
                "flow": "app",
                "target": target,
                "target_id": target_id,
                "scopes": [],
            }
            print(f"[+] Activated App Token for '{role}' (target={target}:{target_id})")

        elif flow == "user":
            token = entry.get("access_token", "").strip()
            refresh = entry.get("refresh_token", "").strip()

            if not token and not refresh:
                raise RuntimeError(f"User token '{name}' must provide 'access_token', 'refresh_token', or both.")

            # Validate-first if access_token is present to avoid burning single-use refresh tokens on quick restarts
            meta = validate_user_token(token, name) if token else None
            if not meta:
                if not refresh:
                    raise RuntimeError(f"Access token for '{name}' is invalid/expired and no 'refresh_token' is set.")
                if not client_secret:
                    raise RuntimeError(f"Token '{name}' requires 'twitch_client_secret' to use 'refresh_token'.")

                refreshed = refresh_user_token(client_id, client_secret, refresh)
                if not refreshed:
                    raise RuntimeError(f"Refresh grant failed for '{name}'.")

                token = refreshed["access_token"]
                entry["access_token"] = token
                if refreshed.get("refresh_token"):
                    entry["refresh_token"] = refreshed["refresh_token"]

                meta = validate_user_token(token, name)
                if not meta:
                    raise RuntimeError(f"Newly refreshed token validation failed for '{name}'.")

            if meta.get("user_id") != target_id:
                raise RuntimeError(
                    f"Token '{name}' validated as user_id={meta.get('user_id')} ({meta.get('login')}), "
                    f"expected {target}={target_id}."
                )

            active_tokens[role] = {
                "access_token": token,
                "flow": "user",
                "target": target,
                "target_id": target_id,
                "scopes": meta.get("scopes", []),
            }
            print(
                f"[+] Activated User Token for '{role}' "
                f"(target={target}:{target_id}, scopes={active_tokens[role]['scopes']})"
            )
        else:
            raise ValueError(f"Unknown flow '{flow}' in token entry '{name}'.")

    return active_tokens, resolved_ids
