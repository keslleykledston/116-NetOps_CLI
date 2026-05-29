from __future__ import annotations

import asyncio

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routes import api, dashboard, diagnostics, l2tp_ipsec, nat, routes, wireguard
from app.security import redirect_after_login
from app.services import heartbeat


settings.ensure_dirs()

app = FastAPI(title="NetOps CLI Connector", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.state.templates = Jinja2Templates(directory="app/templates")

app.include_router(dashboard.router)
app.include_router(wireguard.router)
app.include_router(l2tp_ipsec.router)
app.include_router(routes.router)
app.include_router(nat.router)
app.include_router(diagnostics.router)
app.include_router(api.router)


@app.on_event("startup")
async def start_heartbeat() -> None:
    asyncio.create_task(heartbeat.loop())


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return app.state.templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.web_username and password == settings.web_password:
        request.session["user"] = username
        return redirect_after_login()
    return app.state.templates.TemplateResponse("login.html", {"request": request, "error": "Credenciais invalidas"}, status_code=status.HTTP_401_UNAUTHORIZED)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
