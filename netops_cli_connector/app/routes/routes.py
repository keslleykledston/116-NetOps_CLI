from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security import require_login
from app.services import routing


router = APIRouter(prefix="/routes")


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    require_login(request)
    return request.app.state.templates.TemplateResponse("routes.html", {"request": request, "routes": routing.configured_routes(), "system_routes": routing.system_routes()})


@router.post("/add")
def add_route(
    request: Request,
    destination: str = Form(...),
    gateway: str = Form(""),
    interface: str = Form(""),
    metric: str = Form(""),
    description: str = Form(""),
):
    require_login(request)
    routing.add_route({"destination": destination, "gateway": gateway, "interface": interface, "metric": metric, "description": description})
    return RedirectResponse("/routes", status_code=303)


@router.post("/delete")
def delete_route(request: Request, destination: str = Form(...), confirm: str = Form("")):
    require_login(request)
    if confirm == destination:
        routing.delete_route(destination)
    return RedirectResponse("/routes", status_code=303)
