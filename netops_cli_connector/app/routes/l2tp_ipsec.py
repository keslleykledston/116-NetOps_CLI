from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security import require_login
from app.services import l2tp_ipsec
from app.services.diagnostics import ping


router = APIRouter(prefix="/l2tp-ipsec")


def _context(request: Request, extra: dict | None = None) -> dict:
    context = {
        "request": request,
        "config": l2tp_ipsec.get_config(masked=True),
        "raw": l2tp_ipsec.get_config(),
        "status": l2tp_ipsec.status(),
        "last_action": l2tp_ipsec.last_action(),
        "diagnostics": l2tp_ipsec.diagnostics(),
    }
    if extra:
        context.update(extra)
    return context


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    require_login(request)
    return request.app.state.templates.TemplateResponse("l2tp_ipsec.html", _context(request))


@router.post("/save")
def save(
    request: Request,
    server: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    psk: str = Form(""),
    interface: str = Form("ppp0"),
    remote_network: str = Form(""),
    vpn_routes: str = Form(""),
):
    require_login(request)
    existing = l2tp_ipsec.get_config()
    data = {
        "server": server,
        "username": username,
        "password": password if password and not password.startswith("****") else existing.get("password", ""),
        "psk": psk if psk and not psk.startswith("****") else existing.get("psk", ""),
        "interface": interface,
        "remote_network": remote_network,
        "vpn_routes": vpn_routes,
    }
    l2tp_ipsec.save_config(data)
    return RedirectResponse("/l2tp-ipsec", status_code=303)


@router.post("/up")
def up(request: Request):
    require_login(request)
    l2tp_ipsec.up()
    return RedirectResponse("/l2tp-ipsec", status_code=303)


@router.post("/down")
def down(request: Request):
    require_login(request)
    l2tp_ipsec.down()
    return RedirectResponse("/l2tp-ipsec", status_code=303)


@router.post("/test")
def test(request: Request):
    require_login(request)
    cfg = l2tp_ipsec.get_config()
    host = (cfg.get("remote_network") or cfg.get("server") or "").split("/")[0]
    result = ping(host, 2) if host else None
    return request.app.state.templates.TemplateResponse("l2tp_ipsec.html", _context(request, {"result": result}))
