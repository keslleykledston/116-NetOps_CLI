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
        if value and isinstance(value, str):
            redacted = redacted.replace(value, "********")
    return redacted


def run(
    args: list[str],
    timeout: int = 20,
    sensitive_values: list[str] | None = None,
    env: dict[str, str] | None = None,
    stdin_devnull: bool = False,
    input_text: str | None = None,
) -> CommandResult:
    display = " ".join(shlex.quote(arg) for arg in args)
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            stdin=subprocess.DEVNULL if stdin_devnull else None,
        )
        if input_text is not None:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
        else:
            stdout, stderr = proc.communicate(timeout=timeout)
        return CommandResult(
            command=_redact(display, sensitive_values),
            returncode=proc.returncode,
            stdout=_redact(stdout.strip(), sensitive_values),
            stderr=_redact(stderr.strip(), sensitive_values),
        )
    except FileNotFoundError as exc:
        return CommandResult(display, 127, "", str(exc))
    except subprocess.TimeoutExpired:
        if "proc" in locals():
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
        return CommandResult(display, 124, "", f"timeout after {timeout}s")
