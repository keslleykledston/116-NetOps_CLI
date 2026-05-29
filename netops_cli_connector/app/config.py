from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    connector_name: str = os.getenv("NETOPS_CONNECTOR_NAME", "cliente-a")
    web_username: str = os.getenv("WEB_USERNAME", "admin")
    web_password: str = os.getenv("WEB_PASSWORD", "change-me")
    netops_server_url: str = os.getenv("NETOPS_SERVER_URL", "").rstrip("/")
    connector_token: str = os.getenv("CONNECTOR_TOKEN", "")
    netops_wg_provision_path: str = os.getenv("NETOPS_WG_PROVISION_PATH", "/api/connectors/wireguard/provision")
    wg_interface: str = os.getenv("WG_INTERFACE", "wg-netops")
    lan_interface: str = os.getenv("LAN_INTERFACE", "eth0")
    wan_interface: str = os.getenv("WAN_INTERFACE", "eth0")
    web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
    web_port: int = int(os.getenv("WEB_PORT", "8080"))
    heartbeat_interval_seconds: int = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60"))
    session_secret: str = os.getenv("SESSION_SECRET", "change-this-random-secret")
    config_root: Path = Path(os.getenv("CONFIG_ROOT", "/etc/netops-cli"))

    @property
    def runtime_dir(self) -> Path:
        return self.config_root / "runtime"

    @property
    def wireguard_dir(self) -> Path:
        return self.config_root / "wireguard"

    @property
    def ipsec_dir(self) -> Path:
        return self.config_root / "ipsec"

    @property
    def wg_conf_path(self) -> Path:
        return Path("/etc/wireguard/netops.conf")

    def ensure_dirs(self) -> None:
        for path in [self.config_root, self.runtime_dir, self.wireguard_dir, self.ipsec_dir, Path("/etc/wireguard")]:
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(0o700)


settings = Settings()
