from __future__ import annotations

import os
from typing import Any

from app.config import settings
from app.services.shell import run
from app.storage import read_json, write_json_secure


CONFIG_PATH = settings.runtime_dir / "wireguard.json"


def get_config(masked: bool = False) -> dict[str, Any]:
    from app.storage import scrub

    data = read_json(CONFIG_PATH, {})
    return scrub(data) if masked else data


def save_config(data: dict[str, str]) -> None:
    settings.ensure_dirs()
    write_json_secure(CONFIG_PATH, data)
    conf = render_config(data)
    settings.wg_conf_path.write_text(conf)
    os.chmod(settings.wg_conf_path, 0o600)


def render_config(data: dict[str, str]) -> str:
    endpoint = f"{data.get('endpoint', '')}:{data.get('port', '51820')}"
    keepalive = data.get("keepalive", "25")
    return "\n".join(
        [
            "[Interface]",
            f"Address = {data.get('tunnel_ip', '')}",
            f"PrivateKey = {data.get('private_key', '')}",
            "",
            "[Peer]",
            f"PublicKey = {data.get('server_public_key', '')}",
            f"Endpoint = {endpoint}",
            f"AllowedIPs = {data.get('allowed_ips', '')}",
            f"PersistentKeepalive = {keepalive}",
            "",
        ]
    )


def up():
    return run(["wg-quick", "up", "netops"], timeout=30, sensitive_values=list(get_config().values()))


def down():
    return run(["wg-quick", "down", "netops"], timeout=30, sensitive_values=list(get_config().values()))


def status() -> str:
    link = run(["ip", "link", "show", settings.wg_interface], timeout=5)
    if not link.ok:
        link = run(["ip", "link", "show", "netops"], timeout=5)
    wg = run(["wg", "show"], timeout=5)
    if link.ok:
        return "up"
    if wg.ok and wg.stdout:
        return "up"
    return "down"


def show_logs():
    return run(["sh", "-c", "journalctl -u wg-quick@netops --no-pager -n 80 2>/dev/null || true"], timeout=10)
