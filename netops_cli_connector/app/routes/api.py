from __future__ import annotations

from fastapi import APIRouter, Body, Request

from app.security import require_login
from app.services import diagnostics, firewall, heartbeat, routing
from app.services.status import get_status


router = APIRouter(prefix="/api")


@router.get("/status")
def status(request: Request):
    require_login(request)
    return get_status()


@router.post("/heartbeat")
def send_heartbeat(request: Request):
    require_login(request)
    return heartbeat.send_once()


@router.post("/diagnostics/ping")
def api_ping(request: Request, payload: dict = Body(...)):
    require_login(request)
    result = diagnostics.ping(payload["host"], int(payload.get("count", 4)))
    return result.__dict__


@router.post("/diagnostics/tcp-check")
def api_tcp(request: Request, payload: dict = Body(...)):
    require_login(request)
    return diagnostics.tcp_check(payload["host"], int(payload.get("port", 22)))


@router.post("/diagnostics/udp-check")
def api_udp(request: Request, payload: dict = Body(...)):
    require_login(request)
    return diagnostics.udp_check(payload["host"], int(payload.get("port", 161)))


@router.post("/diagnostics/snmpwalk")
def api_snmp(request: Request, payload: dict = Body(...)):
    require_login(request)
    result = diagnostics.snmpwalk(payload["host"], payload["community"], payload.get("oid", "1.3.6.1.2.1.1.1.0"))
    return result.__dict__


@router.get("/routes")
def api_routes(request: Request):
    require_login(request)
    return {"configured": routing.configured_routes(), "system": routing.system_routes().__dict__}


@router.get("/interfaces")
def api_interfaces(request: Request):
    require_login(request)
    return diagnostics.interfaces().__dict__


@router.get("/firewall")
def api_firewall(request: Request):
    require_login(request)
    fw = firewall.firewall_status()
    return {"iptables_nat": fw["iptables_nat"].__dict__, "nftables": fw["nftables"].__dict__}
