from __future__ import annotations

import socket

from app.services.shell import run


def ping(host: str, count: int = 4):
    return run(["ping", "-c", str(count), "-W", "2", host], timeout=max(8, count * 3))


def traceroute(host: str):
    return run(["traceroute", host], timeout=30)


def tcp_check(host: str, port: int, timeout: int = 5) -> dict[str, str | bool]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return {"ok": True, "message": f"{host}:{port} reachable"}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}


def udp_check(host: str, port: int = 161, timeout: int = 3) -> dict[str, str | bool]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(b"\x00", (host, int(port)))
        return {"ok": True, "message": f"udp packet sent to {host}:{port}"}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}


def snmpwalk(host: str, community: str, oid: str = "1.3.6.1.2.1.1.1.0"):
    return run(["snmpwalk", "-v2c", "-c", community, host, oid], timeout=20, sensitive_values=[community])


def ssh_test(host: str, user: str, port: int = 22):
    return run(
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-p", str(port), f"{user}@{host}", "true"],
        timeout=10,
    )


def interfaces():
    return run(["ip", "-br", "addr"], timeout=10)
