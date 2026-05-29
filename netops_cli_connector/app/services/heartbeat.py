from __future__ import annotations

import asyncio

import requests

from app.config import settings
from app.services.status import get_status, record_heartbeat
from app.services.wireguard import get_provision_settings


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
    provision_settings = get_provision_settings()
    netops_server_url = str(provision_settings.get("netops_server_url") or settings.netops_server_url).rstrip("/")
    connector_token = str(provision_settings.get("connector_token") or settings.connector_token)
    if not netops_server_url or not connector_token:
        result = {"ok": False, "error": "NETOPS_SERVER_URL or CONNECTOR_TOKEN not configured"}
        record_heartbeat(result)
        return result
    if "netops.example.com" in netops_server_url:
        result = {"ok": False, "error": "NETOPS_SERVER_URL still uses the netops.example.com placeholder"}
        record_heartbeat(result)
        return result
    url = f"{netops_server_url}/api/connectors/heartbeat"
    try:
        response = requests.post(
            url,
            json=payload(),
            headers={"Authorization": f"Bearer {connector_token}"},
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
