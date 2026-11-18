# reeloc10bot

A lightweight, zero-dependency Twitch bot module built in standard library Python, leveraging `urllib_inspector` for secure HTTP inspection and API communication.

## Design Philosophy

* **Zero Bloat:** Built strictly on Python's standard library (`urllib.request`, `json`, `os`), avoiding heavy external frameworks.
* **Modular Integration:** Relies on `urllib_inspector` for robust POST/GET payload encoding, redirect handling, and ANSI-colored output tracing.
* **Strict Minimalism:** Designed to run cleanly inside minimal Linux desktop environments without third-party packaging overhead.

## Usage

Set up your credentials and execute the bot by scoping `PYTHONPATH` via `env`:

```bash
env PYTHONPATH="/path/to/urllib_comman_line" python3 bot.py
```

## License

Licensed under the [Apache License 2.0](LICENSE).
