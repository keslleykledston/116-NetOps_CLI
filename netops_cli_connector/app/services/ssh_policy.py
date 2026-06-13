from __future__ import annotations

import re

BLOCKED_SUBSTRINGS = [
    "system-view",
    "configure",
    "conf t",
    "commit",
    "save",
    "delete",
    "remove",
    "reset",
    "reboot",
    "reload",
    "shutdown",
    "undo",
    " set ",
    "edit",
    "copy",
    "write",
    "erase",
    "format",
    "upgrade",
    "install",
    "request system",
]

ALLOWED_PREFIXES = (
    "display",
    "show",
    "ping",
    "traceroute",
    "tracert",
    "screen-length 0 temporary",
    "terminal length 0",
)

SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$()><]")


class SecurityPolicyError(Exception):
    def __init__(self, message: str, exit_code: int = 126):
        super().__init__(message)
        self.exit_code = exit_code


def validate_ssh_command(command: str) -> None:
    trimmed = command.strip()
    if not trimmed:
        raise SecurityPolicyError("Empty SSH command")

    lower = trimmed.lower()
    for blocked in BLOCKED_SUBSTRINGS:
        if blocked in lower:
            raise SecurityPolicyError(f"Blocked by read-only security policy: contains '{blocked.strip()}'")

    if SHELL_METACHAR_PATTERN.search(trimmed):
        raise SecurityPolicyError("Blocked by read-only security policy: shell metacharacters not allowed")

    if not any(lower.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        raise SecurityPolicyError(
            "Blocked by read-only security policy: command must start with display/show/ping/traceroute"
        )
