from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def write_json_secure(path: Path, data: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def mask_secret(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return f"{value[:keep]}{'*' * 8}"


def scrub(data: Any, keys: set[str] | None = None) -> Any:
    secret_keys = keys or {"password", "psk", "private_key", "community", "token", "connector_token"}
    if isinstance(data, dict):
        return {key: (mask_secret(str(value)) if key in secret_keys else scrub(value, secret_keys)) for key, value in data.items()}
    if isinstance(data, list):
        return [scrub(item, secret_keys) for item in data]
    return data
