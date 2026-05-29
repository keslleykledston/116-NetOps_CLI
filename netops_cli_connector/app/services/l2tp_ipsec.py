from __future__ import annotations

import os
import shutil
from typing import Any

from app.config import settings
from app.services.shell import CommandResult, run
from app.storage import read_json, write_json_secure


CONFIG_PATH = settings.runtime_dir / "l2tp_ipsec.json"
LAST_ACTION_PATH = settings.runtime_dir / "l2tp_ipsec_last_action.json"


def get_config(masked: bool = False) -> dict[str, Any]:
    from app.storage import scrub

    data = read_json(CONFIG_PATH, {})
    return scrub(data) if masked else data


def save_config(data: dict[str, str]) -> None:
    settings.ensure_dirs()
    write_json_secure(CONFIG_PATH, data)
    write_files(data)


def _serialize_result(result) -> dict[str, Any]:
    return {
        "command": result.command,
        "returncode": result.returncode,
        "ok": result.ok,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _record_action(action: str, results: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    payload = {
        "action": action,
        "ok": all(item.ok for item in results.values()),
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "results": {name: _serialize_result(result) for name, result in results.items()},
    }
    write_json_secure(LAST_ACTION_PATH, payload)
    return payload


def last_action() -> dict[str, Any]:
    return read_json(LAST_ACTION_PATH, {})


def write_files(data: dict[str, str]) -> None:
    server = data.get("server", "")
    psk = data.get("psk", "")
    user = data.get("username", "")
    password = data.get("password", "")

    (settings.ipsec_dir / "ipsec.conf").write_text(
        "\n".join(
            [
                "config setup",
                "    uniqueids=no",
                "",
                "conn netops-l2tp",
                "    keyexchange=ikev1",
                "    authby=secret",
                "    type=transport",
                "    fragmentation=yes",
                "    forceencaps=yes",
                "    keyingtries=1",
                "    left=%defaultroute",
                "    leftprotoport=17/1701",
                f"    right={server}",
                "    rightid=%any",
                "    rightprotoport=17/1701",
                "    dpdaction=clear",
                "    dpddelay=30s",
                "    dpdtimeout=120s",
                "    ikelifetime=8h",
                "    lifetime=1h",
                "    ike=aes256-sha1-modp1024,aes128-sha1-modp1024,3des-sha1-modp1024",
                "    esp=aes256-sha1,aes128-sha1,3des-sha1",
                "    auto=add",
                "",
            ]
        )
    )
    (settings.ipsec_dir / "ipsec.secrets").write_text(f": PSK \"{psk}\"\n")
    (settings.ipsec_dir / "xl2tpd.conf").write_text(
        "\n".join(
            [
                "[global]",
                "access control = no",
                "",
                "[lac netops-l2tp]",
                f"lns = {server}",
                "ppp debug = no",
                "pppoptfile = /etc/netops-cli/ipsec/options.xl2tpd",
                "length bit = yes",
                "redial = no",
                "autodial = no",
                "",
            ]
        )
    )
    (settings.ipsec_dir / "options.xl2tpd").write_text(
        "\n".join(
            [
                "ipcp-accept-local",
                "ipcp-accept-remote",
                "refuse-eap",
                "require-mschap-v2",
                "noccp",
                "noauth",
                "nodefaultroute",
                "noipdefault",
                "maxfail 1",
                "lcp-echo-interval 20",
                "lcp-echo-failure 3",
                "mtu 1280",
                "mru 1280",
                f"name {user}",
                f"password {password}",
                "",
            ]
        )
    )
    for path in settings.ipsec_dir.iterdir():
        os.chmod(path, 0o600)
    shutil.copyfile(settings.ipsec_dir / "ipsec.conf", "/etc/ipsec.conf")
    shutil.copyfile(settings.ipsec_dir / "ipsec.secrets", "/etc/ipsec.secrets")
    os.chmod("/etc/ipsec.secrets", 0o600)
    os.makedirs("/etc/xl2tpd", exist_ok=True)
    shutil.copyfile(settings.ipsec_dir / "xl2tpd.conf", "/etc/xl2tpd/xl2tpd.conf")
    run(["ipsec", "rereadall"], timeout=10, sensitive_values=[psk, password])
    run(["ipsec", "update"], timeout=10, sensitive_values=[psk, password])


def up():
    cfg = get_config()
    sensitive = [cfg.get("password", ""), cfg.get("psk", "")]
    run(["sh", "-c", "echo 'd netops-l2tp' > /var/run/xl2tpd/l2tp-control || true"], timeout=5, sensitive_values=sensitive)
    run(["ipsec", "down", "netops-l2tp"], timeout=15, sensitive_values=sensitive)
    ipsec = run(["ipsec", "up", "netops-l2tp"], timeout=45, sensitive_values=sensitive)
    if ipsec.ok:
        l2tp = run(["sh", "-c", "echo 'c netops-l2tp' > /var/run/xl2tpd/l2tp-control"], timeout=10, sensitive_values=sensitive)
    else:
        run(["ipsec", "down", "netops-l2tp"], timeout=15, sensitive_values=sensitive)
        l2tp = CommandResult(
            command="xl2tpd connect netops-l2tp",
            returncode=125,
            stdout="",
            stderr="skipped because IPsec did not establish successfully",
        )
    return _record_action("connect", {"ipsec": ipsec, "l2tp": l2tp})


def down():
    cfg = get_config()
    sensitive = [cfg.get("password", ""), cfg.get("psk", "")]
    l2tp = run(["sh", "-c", "echo 'd netops-l2tp' > /var/run/xl2tpd/l2tp-control || true"], timeout=10, sensitive_values=sensitive)
    ipsec = run(["ipsec", "down", "netops-l2tp"], timeout=30, sensitive_values=sensitive)
    return _record_action("disconnect", {"ipsec": ipsec, "l2tp": l2tp})


def status() -> str:
    cfg = get_config()
    iface = cfg.get("interface", "ppp0")
    link = run(["ip", "link", "show", iface], timeout=5)
    return "up" if link.ok else "down"


def diagnostics() -> dict[str, Any]:
    cfg = get_config()
    iface = cfg.get("interface", "ppp0")
    checks = {
        "ipsec_status": run(["ipsec", "statusall"], timeout=10),
        "l2tp_interface": run(["ip", "-d", "addr", "show", iface], timeout=5),
        "routes": run(["ip", "route", "show"], timeout=5),
        "xfrm_state": run(["ip", "xfrm", "state"], timeout=5),
        "xfrm_policy": run(["ip", "xfrm", "policy"], timeout=5),
        "processes": run(["sh", "-c", "pgrep -af 'charon|starter|xl2tpd|pppd' || true"], timeout=5),
        "logs": show_logs(),
    }
    return {name: _serialize_result(result) for name, result in checks.items()}


def show_logs():
    return run(
        [
            "sh",
            "-c",
            "journalctl -u strongswan --no-pager -n 80 2>/dev/null; "
            "journalctl -u strongswan-starter --no-pager -n 80 2>/dev/null; "
            "journalctl -u xl2tpd --no-pager -n 80 2>/dev/null; "
            "tail -n 80 /var/log/syslog /var/log/auth.log 2>/dev/null || true",
        ],
        timeout=10,
    )
