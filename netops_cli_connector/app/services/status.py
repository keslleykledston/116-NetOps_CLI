from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.services import firewall, l2tp_ipsec, routing, wireguard
from app.services.diagnostics import interfaces
from app.storage import read_json, write_json_secure


HEARTBEAT_PATH = settings.runtime_dir / "heartbeat.json"


def detect_default_interface() -> str:
    route = routing.system_routes()
    for line in route.stdout.splitlines():
        if line.startswith("default "):
            parts = line.split()
            if "dev" in parts:
                return parts[parts.index("dev") + 1]
    return settings.wan_interface


def heartbeat_state() -> dict:
    return read_json(HEARTBEAT_PATH, {})


def record_heartbeat(result: dict) -> None:
    result["sent_at"] = datetime.now(timezone.utc).isoformat()
    write_json_secure(HEARTBEAT_PATH, result)


def get_status() -> dict:
    routes = routing.configured_routes()
    nat = firewall.get_nat()
    return {
        "connector_name": wireguard.connector_name(),
        "status": "online",
        "wan_interface": detect_default_interface(),
        "lan_interface": settings.lan_interface,
        "configured_wan_interface": settings.wan_interface,
        "wireguard_status": wireguard.status(),
        "wireguard_stats": wireguard.stats(),
        "l2tp_ipsec_status": l2tp_ipsec.status(),
        "routes_count": len(routes),
        "routes": routes,
        "nat_enabled": bool(nat.get("enabled")),
        "nat": nat,
        "interfaces": interfaces().stdout,
        "system_routes": routing.system_routes().stdout,
        "last_heartbeat": heartbeat_state(),
    }
