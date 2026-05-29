from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.shell import run
from app.storage import read_json, write_json_secure


CONFIG_PATH = settings.runtime_dir / "nat.json"


def get_nat() -> dict[str, Any]:
    return read_json(CONFIG_PATH, {"enabled": False})


def _rule_args(config: dict[str, Any]) -> list[str]:
    args = ["iptables", "-t", "nat", "-C", "POSTROUTING"]
    if config.get("source_network"):
        args += ["-s", config["source_network"]]
    if config.get("out_interface"):
        args += ["-o", config["out_interface"]]
    args += ["-j", "MASQUERADE"]
    return args


def enable_nat(config: dict[str, Any]):
    config = {**config, "enabled": True}
    write_json_secure(CONFIG_PATH, config)
    if config.get("enable_forwarding"):
        run(["sysctl", "-w", "net.ipv4.ip_forward=1"], timeout=5)
    check = run(_rule_args(config), timeout=5)
    if check.ok:
        return check
    add_args = _rule_args(config)
    add_args[3] = "-A"
    return run(add_args, timeout=10)


def disable_nat():
    config = get_nat()
    config["enabled"] = False
    write_json_secure(CONFIG_PATH, config)
    check = run(_rule_args(config), timeout=5)
    if not check.ok:
        return check
    del_args = _rule_args(config)
    del_args[3] = "-D"
    return run(del_args, timeout=10)


def firewall_status():
    nft = run(["nft", "list", "ruleset"], timeout=10)
    ipt = run(["iptables", "-t", "nat", "-S"], timeout=10)
    return {"nftables": nft, "iptables_nat": ipt}
