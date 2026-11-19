# reeloc10bot

A lightweight, minimal dependency Twitch bot module built in standard library Python, leveraging `urllib_inspector` for secure HTTP inspection and API communication.

## Design Philosophy

* **Minimal Bloat:** Built strictly on Python's standard library (`urllib.request`, `json`, `os`), avoiding heavy external frameworks.
* **Modular Integration:** Relies on `urllib_inspector` for robust POST/GET payload encoding, redirect handling, and ANSI-colored output tracing.
* **Strict Minimalism:** Designed to run cleanly inside minimal Linux desktop environments without third-party packaging overhead.

## Acquiring tokens

config.reduced.json : ["twitch_client_id"] only required.

```bash
env PYTHONPATH=../urllib-inspector BOT_TOKEN_CONFIG=<secrets>/config.reduced.json python3 bot_acquire_token_by_device.py channel:read:redemptions
```

Login while using the approval link determines the id of the granter (broadcaster / bot logins).

## Revoking tokens

config.revoke.json containing ["twitch_client_id", "twitch_user_token"] only

```bash
env PYTHONPATH=../urllib-inspector BOT_CONFIG=<secrets>/config.revoke.json python3 revoke_access_token.py
```

## Usage

Execute the bot by scoping `PYTHONPATH` via `env`:

```bash
env PYTHONPATH="/path/to/urllib-inspector" python3 bot.py
```

## License

Licensed under the [Apache License 2.0](LICENSE).
