from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _redact(text: str, sensitive_values: list[str] | None) -> str:
    redacted = text
    for value in sensitive_values or []:
        if value:
            redacted = redacted.replace(value, "********")
    return redacted


def run(args: list[str], timeout: int = 20, sensitive_values: list[str] | None = None) -> CommandResult:
    display = " ".join(shlex.quote(arg) for arg in args)
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return CommandResult(
            command=_redact(display, sensitive_values),
            returncode=proc.returncode,
            stdout=_redact(proc.stdout.strip(), sensitive_values),
            stderr=_redact(proc.stderr.strip(), sensitive_values),
        )
    except FileNotFoundError as exc:
        return CommandResult(display, 127, "", str(exc))
    except subprocess.TimeoutExpired:
        return CommandResult(display, 124, "", f"timeout after {timeout}s")
