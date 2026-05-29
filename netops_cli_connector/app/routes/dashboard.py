from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.security import require_login
from app.services.status import get_status


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    require_login(request)
    return request.app.state.templates.TemplateResponse("dashboard.html", {"request": request, "status": get_status()})
