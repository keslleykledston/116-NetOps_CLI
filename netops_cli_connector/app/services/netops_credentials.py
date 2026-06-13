from __future__ import annotations

from app.config import settings
from app.services.wireguard import get_provision_settings


def resolve_netops_credentials() -> tuple[str, str]:
    """Return (netops_server_url, connector_token) from runtime provision or env."""
    provision = get_provision_settings()
    url = str(provision.get("netops_server_url") or settings.netops_server_url).strip().rstrip("/")
    token = str(provision.get("connector_token") or settings.connector_token).strip()
    return url, token


def credentials_configured() -> bool:
    url, token = resolve_netops_credentials()
    if not url or not token or token == "change-me":
        return False
    if "netops.example.com" in url:
        return False
    return True
