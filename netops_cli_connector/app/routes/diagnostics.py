from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.security import require_login
from app.services import diagnostics, firewall, l2tp_ipsec, routing, wireguard


router = APIRouter(prefix="/diagnostics")


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    require_login(request)
    return request.app.state.templates.TemplateResponse("diagnostics.html", {"request": request})


@router.post("/ping", response_class=HTMLResponse)
def ping_page(request: Request, host: str = Form(...)):
    require_login(request)
    return request.app.state.templates.TemplateResponse("diagnostics.html", {"request": request, "result": diagnostics.ping(host)})


@router.post("/traceroute", response_class=HTMLResponse)
def traceroute_page(request: Request, host: str = Form(...)):
    require_login(request)
    return request.app.state.templates.TemplateResponse("diagnostics.html", {"request": request, "result": diagnostics.traceroute(host)})


@router.post("/tcp", response_class=HTMLResponse)
def tcp_page(request: Request, host: str = Form(...), port: int = Form(...)):
    require_login(request)
    return request.app.state.templates.TemplateResponse("diagnostics.html", {"request": request, "json_result": diagnostics.tcp_check(host, port)})


@router.post("/udp", response_class=HTMLResponse)
def udp_page(request: Request, host: str = Form(...), port: int = Form(161)):
    require_login(request)
    return request.app.state.templates.TemplateResponse("diagnostics.html", {"request": request, "json_result": diagnostics.udp_check(host, port)})


@router.post("/snmp", response_class=HTMLResponse)
def snmp_page(request: Request, host: str = Form(...), community: str = Form(...), oid: str = Form("1.3.6.1.2.1.1.1.0")):
    require_login(request)
    return request.app.state.templates.TemplateResponse("diagnostics.html", {"request": request, "result": diagnostics.snmpwalk(host, community, oid)})


@router.get("/system", response_class=HTMLResponse)
def system_page(request: Request):
    require_login(request)
    fw = firewall.firewall_status()
    return request.app.state.templates.TemplateResponse(
        "diagnostics.html",
        {
            "request": request,
            "system": {
                "interfaces": diagnostics.interfaces(),
                "routes": routing.system_routes(),
                "iptables": fw["iptables_nat"],
                "nftables": fw["nftables"],
                "wireguard_logs": wireguard.show_logs(),
                "l2tp_ipsec_logs": l2tp_ipsec.show_logs(),
            },
        },
    )
