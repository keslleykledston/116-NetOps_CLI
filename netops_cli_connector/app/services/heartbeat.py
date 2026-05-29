from __future__ import annotations

import asyncio

import requests

from app.config import settings
from app.services.status import get_status, record_heartbeat


def payload() -> dict:
    status = get_status()
    return {
        "connector_name": status["connector_name"],
        "status": "online",
        "wireguard_status": status["wireguard_status"],
        "l2tp_ipsec_status": status["l2tp_ipsec_status"],
        "lan_interface": status["lan_interface"],
        "wan_interface": status["wan_interface"],
        "routes_count": status["routes_count"],
        "nat_enabled": status["nat_enabled"],
    }


def send_once() -> dict:
    if not settings.netops_server_url or not settings.connector_token:
        result = {"ok": False, "error": "NETOPS_SERVER_URL or CONNECTOR_TOKEN not configured"}
        record_heartbeat(result)
        return result
    url = f"{settings.netops_server_url}/api/connectors/heartbeat"
    try:
        response = requests.post(
            url,
            json=payload(),
            headers={"Authorization": f"Bearer {settings.connector_token}"},
            timeout=10,
        )
        result = {"ok": response.ok, "status_code": response.status_code, "response": response.text[:500]}
    except requests.RequestException as exc:
        result = {"ok": False, "error": str(exc)}
    record_heartbeat(result)
    return result


async def loop() -> None:
    while True:
        await asyncio.to_thread(send_once)
        await asyncio.sleep(settings.heartbeat_interval_seconds)
