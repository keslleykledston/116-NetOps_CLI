from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security import require_login
from app.services import firewall


router = APIRouter(prefix="/nat")


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    require_login(request)
    return request.app.state.templates.TemplateResponse("nat.html", {"request": request, "nat": firewall.get_nat(), "firewall": firewall.firewall_status()})


@router.post("/enable")
def enable(
    request: Request,
    in_interface: str = Form(""),
    out_interface: str = Form(...),
    source_network: str = Form(...),
    enable_forwarding: str = Form("off"),
):
    require_login(request)
    firewall.enable_nat({"in_interface": in_interface, "out_interface": out_interface, "source_network": source_network, "enable_forwarding": enable_forwarding == "on"})
    return RedirectResponse("/nat", status_code=303)


@router.post("/disable")
def disable(request: Request, confirm: str = Form("")):
    require_login(request)
    if confirm == "DISABLE":
        firewall.disable_nat()
    return RedirectResponse("/nat", status_code=303)
