from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security import require_login
from app.services import wireguard
from app.services.diagnostics import ping


router = APIRouter(prefix="/wireguard")


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    require_login(request)
    return request.app.state.templates.TemplateResponse(
        "wireguard.html",
        {
            "request": request,
            "config": wireguard.get_config(masked=True),
            "raw": wireguard.get_config(),
            "status": wireguard.status(),
            "last_provision": wireguard.last_provision(),
            "client_public_key": wireguard.local_public_key(),
        },
    )


@router.post("/save")
def save(
    request: Request,
    endpoint: str = Form(""),
    port: str = Form("51820"),
    private_key: str = Form(""),
    server_public_key: str = Form(""),
    allowed_ips: str = Form(""),
    tunnel_ip: str = Form(""),
    keepalive: str = Form("25"),
):
    require_login(request)
    existing = wireguard.get_config()
    data = {
        "endpoint": endpoint,
        "port": port,
        "private_key": private_key if private_key and not private_key.startswith("****") else existing.get("private_key", ""),
        "server_public_key": server_public_key,
        "allowed_ips": allowed_ips,
        "tunnel_ip": tunnel_ip,
        "keepalive": keepalive,
    }
    wireguard.save_config(data)
    return RedirectResponse("/wireguard", status_code=303)


@router.post("/up")
def up(request: Request):
    require_login(request)
    wireguard.up()
    return RedirectResponse("/wireguard", status_code=303)


@router.post("/provision")
def provision(request: Request):
    require_login(request)
    wireguard.provision_with_token()
    return RedirectResponse("/wireguard", status_code=303)


@router.post("/down")
def down(request: Request):
    require_login(request)
    wireguard.down()
    return RedirectResponse("/wireguard", status_code=303)


@router.post("/test")
def test(request: Request):
    require_login(request)
    cfg = wireguard.get_config()
    first_allowed = (cfg.get("allowed_ips") or "10.255.0.1").split(",")[0].strip().split("/")[0]
    result = ping(first_allowed, 2)
    return request.app.state.templates.TemplateResponse(
        "wireguard.html",
        {
            "request": request,
            "config": wireguard.get_config(masked=True),
            "raw": cfg,
            "status": wireguard.status(),
            "result": result,
            "last_provision": wireguard.last_provision(),
            "client_public_key": wireguard.local_public_key(),
        },
    )
