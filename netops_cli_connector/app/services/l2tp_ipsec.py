from __future__ import annotations

import os
import shutil
import time
from typing import Any

from app.config import settings
from app.services.shell import CommandResult, run
from app.storage import read_json, write_json_secure


CONFIG_PATH = settings.runtime_dir / "l2tp_ipsec.json"
LAST_ACTION_PATH = settings.runtime_dir / "l2tp_ipsec_last_action.json"
# Mikrotik ROS 6 default profile: enc=aes-128,3des hash=sha1 dh=modp2048,modp1024 lifetime=1d
# Mikrotik ROS 6 default proposal: enc=aes-256/192/128-cbc auth=sha1 pfs=modp1024 lifetime=30m
DEFAULT_IKE_PROPOSALS = "aes128-sha1-modp2048,aes128-sha1-modp1024,3des-sha1-modp2048,3des-sha1-modp1024"
DEFAULT_ESP_PROPOSALS = "aes128-sha1-modp1024,aes192-sha1-modp1024,aes256-sha1-modp1024,3des-sha1-modp1024"
MIKROTIK_IKE_LIFETIME = "1d"
MIKROTIK_ESP_LIFETIME = "30m"
MIKROTIK_DPD_DELAY = "120s"

IPSEC_UP_FAILURE_MARKERS = (
    "establishing connection 'netops-l2tp' failed",
    "destroying ike_sa",
    "no proposal chosen",
    "authentication failed",
    "parsed informational",
)


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


def _ipsec_status_established(result: CommandResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}"
    return "netops-l2tp" in text and ("ESTABLISHED" in text or "INSTALLED" in text)


def _ipsec_up_failed(result: CommandResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    return any(marker in text for marker in IPSEC_UP_FAILURE_MARKERS)


def _failed_ipsec_result(result: CommandResult, message: str) -> CommandResult:
    stderr = "\n".join(part for part in [result.stderr, message] if part)
    return CommandResult(result.command, 125, result.stdout, stderr)


def last_action() -> dict[str, Any]:
    return read_json(LAST_ACTION_PATH, {})


def write_files(data: dict[str, str]) -> None:
    server = data.get("server", "")
    local_address = data.get("local_address", "").strip() or "%defaultroute"
    local_id = data.get("local_id", "").strip()
    ike_proposals = data.get("ike_proposals", "").strip() or DEFAULT_IKE_PROPOSALS
    esp_proposals = data.get("esp_proposals", "").strip() or DEFAULT_ESP_PROPOSALS
    psk = data.get("psk", "")
    user = data.get("username", "")
    password = data.get("password", "")

    # Mikrotik L2TP dynamic peer matches catch-all PSK; explicit leftid often breaks phase1.
    local_id_lines = [f"    leftid={local_id}"] if local_id else []
    xl2tpd_listen_lines = [] if local_address == "%defaultroute" else [f"listen-addr = {local_address}"]
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
                f"    left={local_address}",
                *local_id_lines,
                "    leftprotoport=17/1701",
                f"    right={server}",
                "    rightid=%any",
                "    rightprotoport=17/1701",
                "    dpdaction=clear",
                f"    dpddelay={MIKROTIK_DPD_DELAY}",
                "    dpdtimeout=120s",
                f"    ikelifetime={MIKROTIK_IKE_LIFETIME}",
                f"    lifetime={MIKROTIK_ESP_LIFETIME}",
                f"    ike={ike_proposals}",
                f"    esp={esp_proposals}",
                "    auto=add",
                "",
            ]
        )
    )
    # Catch-all PSK — required for Mikrotik L2TP server dynamic ipsec peer (use-ipsec=yes).
    (settings.ipsec_dir / "ipsec.secrets").write_text(f": PSK \"{psk}\"\n")
    (settings.ipsec_dir / "xl2tpd.conf").write_text(
        "\n".join(
            [
                "[global]",
                "access control = no",
                *xl2tpd_listen_lines,
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


def _wait_for_ipsec_ready(sensitive: list[str], timeout_s: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = run(["ipsec", "status"], timeout=5, sensitive_values=sensitive)
        if status.ok and "Security Associations" in status.stdout:
            return True
        time.sleep(0.5)
    return False


def _ensure_xl2tpd_running(sensitive: list[str]) -> CommandResult:
    return run(
        [
            "sh",
            "-c",
            "mkdir -p /var/run/xl2tpd; "
            "if [ ! -p /var/run/xl2tpd/l2tp-control ]; then rm -f /var/run/xl2tpd/l2tp-control; fi; "
            "pgrep -x xl2tpd >/dev/null || xl2tpd; "
            "sleep 1; "
            "pgrep -x xl2tpd >/dev/null",
        ],
        timeout=8,
        sensitive_values=sensitive,
    )


def _wait_for_ppp_interface(iface: str, timeout_s: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        link = run(["ip", "link", "show", iface], timeout=5)
        if link.ok:
            return True
        time.sleep(1.0)
    return False


def _apply_static_routes() -> dict[str, CommandResult]:
    from app.services import routing

    return {f"route_{index}": result for index, result in enumerate(routing.apply_all(), start=1)}


def up():
    cfg = get_config()
    sensitive = [cfg.get("password", ""), cfg.get("psk", "")]
    iface = cfg.get("interface", "ppp0")
    results: dict[str, CommandResult] = {}
    if not _wait_for_ipsec_ready(sensitive):
        return _record_action(
            "connect",
            {
                "ipsec": CommandResult("ipsec ready check", 125, "", "strongSwan charon not ready"),
                "l2tp": CommandResult("xl2tpd connect netops-l2tp", 125, "", "skipped because charon is not ready"),
            },
        )
    xl2tpd = _ensure_xl2tpd_running(sensitive)
    results["xl2tpd"] = xl2tpd
    if not xl2tpd.ok:
        return _record_action(
            "connect",
            {
                **results,
                "ipsec": CommandResult("ipsec up netops-l2tp", 125, "", "skipped because xl2tpd is not running"),
                "l2tp": CommandResult("xl2tpd connect netops-l2tp", 125, "", "skipped because xl2tpd is not running"),
            },
        )
    run(["sh", "-c", "echo 'd netops-l2tp' > /var/run/xl2tpd/l2tp-control || true"], timeout=5, sensitive_values=sensitive)
    run(["ipsec", "down", "netops-l2tp"], timeout=15, sensitive_values=sensitive)
    ipsec = run(["ipsec", "up", "netops-l2tp"], timeout=45, sensitive_values=sensitive)
    if ipsec.ok and _ipsec_up_failed(ipsec):
        ipsec = _failed_ipsec_result(ipsec, "ipsec up returned rc=0, but the output reports that the IKE_SA was destroyed or the connection failed.")
    results["ipsec"] = ipsec
    if ipsec.ok:
        ipsec_status = run(["ipsec", "statusall"], timeout=10, sensitive_values=sensitive)
        results["ipsec_status"] = ipsec_status
        if _ipsec_status_established(ipsec_status):
            l2tp = run(["sh", "-c", "echo 'c netops-l2tp' > /var/run/xl2tpd/l2tp-control"], timeout=10, sensitive_values=sensitive)
            if l2tp.ok and not _wait_for_ppp_interface(iface):
                l2tp = _failed_ipsec_result(
                    l2tp,
                    f"L2TP control sent but {iface} did not come up; check PPP user/password on Mikrotik /ppp secret.",
                )
            elif l2tp.ok:
                results.update(_apply_static_routes())
        else:
            ipsec = _failed_ipsec_result(ipsec, "ipsec statusall did not show netops-l2tp as ESTABLISHED/INSTALLED; L2TP was not started.")
            results["ipsec"] = ipsec
            run(["ipsec", "down", "netops-l2tp"], timeout=15, sensitive_values=sensitive)
            l2tp = CommandResult(
                command="xl2tpd connect netops-l2tp",
                returncode=125,
                stdout="",
                stderr="skipped because IPsec did not establish successfully",
            )
    else:
        run(["ipsec", "down", "netops-l2tp"], timeout=15, sensitive_values=sensitive)
        l2tp = CommandResult(
            command="xl2tpd connect netops-l2tp",
            returncode=125,
            stdout="",
            stderr="skipped because IPsec did not establish successfully",
        )
    results["l2tp"] = l2tp
    return _record_action("connect", results)


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
    server = cfg.get("server", "")
    checks = {
        "ipsec_status": run(["ipsec", "statusall"], timeout=10),
        "l2tp_interface": run(["ip", "-d", "addr", "show", iface], timeout=5),
        "routes": run(["ip", "route", "show"], timeout=5),
        "server_route": run(["ip", "route", "get", server], timeout=5) if server else CommandResult("ip route get <server>", 125, "", "server is not configured"),
        "udp_500": run(["nc", "-zvu", "-w", "2", server, "500"], timeout=5) if server else CommandResult("nc -zvu -w 2 <server> 500", 125, "", "server is not configured"),
        "udp_4500": run(["nc", "-zvu", "-w", "2", server, "4500"], timeout=5) if server else CommandResult("nc -zvu -w 2 <server> 4500", 125, "", "server is not configured"),
        "udp_1701": run(["nc", "-zvu", "-w", "2", server, "1701"], timeout=5) if server else CommandResult("nc -zvu -w 2 <server> 1701", 125, "", "server is not configured"),
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
