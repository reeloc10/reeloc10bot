# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 reeloc10

import random
import re
import time
from collections.abc import Callable

BOOT_TIME = time.time()


def get_uptime() -> str:
    """Calculate elapsed uptime from module import time."""
    seconds = int(time.time() - BOOT_TIME)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# 100% Public Domain & Open Engineering Wisdom Pool
WISDOM_POOL: list[str] = [
    "Simplicity is the ultimate sophistication. — Leonardo da Vinci",
    "The impediment to action advances action. What stands in the way becomes the way. — Marcus Aurelius",
    "Do one thing and do it well. — The Unix Philosophy",
    "Silence is a source of great strength. — Lao Tzu",
    "Make everything as simple as possible, but not simpler. — Classic Axiom",
    "He who has a why to live can bear almost any how. — Friedrich Nietzsche",
    "Perfection is achieved, not when there is nothing more to add, but when there is nothing left to take away. — Antoine de Saint-Exupéry",
    "Quiet minds withstand storms better than turbulent oceans.",
    "A clean kernel log is a quiet mind.",
    "First, solve the problem. Then, write the code. — John Johnson",
]

GITHUB_REPOSITORIES: list[str] = [
        "https://github.com/reeloc10/tiny_python_nvim_debugger.git",
        "https://github.com/reeloc10/urllib-inspector.git",
        "https://github.com/reeloc10/reeloc10bot.git"
]


def handle_ping(chatter: str, args: list[str]) -> str:
    return "Pong, running smooth on Fedora 45."


def handle_uptime(chatter: str, args: list[str]) -> str:
    return f"All systems operational. Uptime: {get_uptime()}."


def handle_specs(chatter: str, args: list[str]) -> str:
    return "CPU: Intel Core i7-6700K | OS: Fedora 45 (GNOME) | Audio: PipeWire."


def handle_wisdom(chatter: str, args: list[str]) -> str:
    """Pick a random piece of copyright-free wisdom."""
    return f"@{chatter} ➔ {random.choice(WISDOM_POOL)}"


def handle_repos(chatter: str, args: list[str]) -> str:
    """List active repositories."""
    repos_list = ", ".join(GITHUB_REPOSITORIES)
    return f"Repositories: {repos_list} (GitHub: reeloc10) | Licensed under Apache-2.0."


def handle_python(chatter: str, args: list[str]) -> str:
    """Highlight the rare zero-pip Python EventSub architecture."""
    return "Twitch docs may lack Python refs (only Node/Go/C#) - POC of a custom zero-pip stdlib Python EventSub WebSocket bot."


def handle_commands(chatter: str, args: list[str]) -> str:
    """Dynamically list all registered commands and point to example architecture."""
    cmds = ", ".join(sorted(COMMAND_REGISTRY.keys()))
    return f"Commands: {cmds} | Built with zero-pip Python EventSub WebSockets."


def handle_bot_mention(chatter: str, args: list[str]) -> str:
    return f"I am meditating at my Fedora 45 haven, @{chatter}."


# Command Registry mapping command names to handler functions
COMMAND_REGISTRY: dict[str, Callable[[str, list[str]], str]] = {
    "!ping": handle_ping,
    "!uptime": handle_uptime,
    "!specs": handle_specs,
    "!wisdom": handle_wisdom,
    "!repos": handle_repos,
    "!python": handle_python,
    "!commands": handle_commands,
}

COMMAND_RE = re.compile(r"^(![a-zA-Z0-9_-]+)(?:\s+(.*))?", re.IGNORECASE)
BOT_MENTION_RE = re.compile(r"^bot(?:\s|[?,!:]|$)", re.IGNORECASE)


def evaluate_message(text: str, chatter: str) -> str | None:
    """Parse text, extract command and arguments, and dispatch to the correct handler."""
    text = text.strip()

    # 1. Check for explicit bang commands
    match = COMMAND_RE.match(text)
    if match:
        cmd = match.group(1).lower()
        args_str = match.group(2) or ""
        args = args_str.split() if args_str else []

        if cmd in COMMAND_REGISTRY:
            return COMMAND_REGISTRY[cmd](chatter, args)

    # 2. Check for conversational bot mentions
    if BOT_MENTION_RE.match(text):
        return handle_bot_mention(chatter, [])

    return None
