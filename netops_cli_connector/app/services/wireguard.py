from __future__ import annotations

import os
from typing import Any

import requests

from app.config import settings
from app.services.shell import run
from app.storage import read_json, write_json_secure


CONFIG_PATH = settings.runtime_dir / "wireguard.json"
LAST_PROVISION_PATH = settings.runtime_dir / "wireguard_last_provision.json"


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


def _command_to_dict(result) -> dict[str, Any]:
    return {
        "command": result.command,
        "returncode": result.returncode,
        "ok": result.ok,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _record_provision(payload: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    payload["ran_at"] = datetime.now(timezone.utc).isoformat()
    write_json_secure(LAST_PROVISION_PATH, payload)
    return payload


def last_provision() -> dict[str, Any]:
    return read_json(LAST_PROVISION_PATH, {})


def generate_keypair() -> dict[str, str]:
    private = run(["wg", "genkey"], timeout=5)
    if not private.ok or not private.stdout:
        raise RuntimeError(private.stderr or "failed to generate WireGuard private key")
    public = run(["sh", "-c", f"printf '%s' '{private.stdout}' | wg pubkey"], timeout=5, sensitive_values=[private.stdout])
    if not public.ok or not public.stdout:
        raise RuntimeError(public.stderr or "failed to derive WireGuard public key")
    return {"private_key": private.stdout.strip(), "public_key": public.stdout.strip()}


def local_public_key() -> str:
    cfg = get_config()
    private_key = cfg.get("private_key")
    if not private_key:
        return ""
    public = run(["sh", "-c", f"printf '%s' '{private_key}' | wg pubkey"], timeout=5, sensitive_values=[private_key])
    return public.stdout.strip() if public.ok else ""


def _first(data: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return str(value)
    return default


def _normalize_provision_response(response: dict[str, Any]) -> dict[str, str]:
    data = response.get("wireguard") if isinstance(response.get("wireguard"), dict) else response
    endpoint_value = _first(data, "endpoint", "server_endpoint", "host")
    port = _first(data, "port", "server_port", default="51820")
    if ":" in endpoint_value and not endpoint_value.startswith("["):
        host, maybe_port = endpoint_value.rsplit(":", 1)
        if maybe_port.isdigit():
            endpoint_value = host
            port = maybe_port
    return {
        "endpoint": endpoint_value,
        "port": port,
        "server_public_key": _first(data, "server_public_key", "public_key"),
        "allowed_ips": _first(data, "allowed_ips", "allowedIPs", default="10.255.0.1/32"),
        "tunnel_ip": _first(data, "tunnel_ip", "client_tunnel_ip", "address"),
        "keepalive": _first(data, "keepalive", "persistent_keepalive", "persistentKeepalive", default="25"),
    }


def provision_with_token() -> dict[str, Any]:
    if not settings.netops_server_url or not settings.connector_token:
        return _record_provision({"ok": False, "error": "NETOPS_SERVER_URL or CONNECTOR_TOKEN not configured"})

    cfg = get_config()
    if cfg.get("private_key"):
        private_key = cfg["private_key"]
        public_result = run(["sh", "-c", f"printf '%s' '{private_key}' | wg pubkey"], timeout=5, sensitive_values=[private_key])
        if not public_result.ok:
            return _record_provision({"ok": False, "error": public_result.stderr, "public_key": ""})
        public_key = public_result.stdout.strip()
    else:
        keys = generate_keypair()
        private_key = keys["private_key"]
        public_key = keys["public_key"]

    url = f"{settings.netops_server_url}{settings.netops_wg_provision_path}"
    request_payload = {
        "connector_name": settings.connector_name,
        "public_key": public_key,
        "wireguard_interface": settings.wg_interface,
        "lan_interface": settings.lan_interface,
        "wan_interface": settings.wan_interface,
    }
    try:
        response = requests.post(
            url,
            json=request_payload,
            headers={"Authorization": f"Bearer {settings.connector_token}"},
            timeout=20,
        )
    except requests.RequestException as exc:
        return _record_provision({"ok": False, "error": str(exc), "public_key": public_key})

    if not response.ok:
        return _record_provision(
            {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text[:500],
                "public_key": public_key,
            }
        )

    try:
        provision_data = response.json()
    except ValueError:
        return _record_provision({"ok": False, "error": "provision response is not valid JSON", "public_key": public_key})

    normalized = _normalize_provision_response(provision_data)
    missing = [key for key in ["endpoint", "server_public_key", "allowed_ips", "tunnel_ip"] if not normalized.get(key)]
    if missing:
        return _record_provision({"ok": False, "error": f"missing fields in provision response: {', '.join(missing)}", "public_key": public_key})

    saved = {**cfg, **normalized, "private_key": private_key, "client_public_key": public_key, "provisioned": True}
    save_config(saved)
    return _record_provision({"ok": True, "public_key": public_key, "config": {k: v for k, v in saved.items() if k != "private_key"}})


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
