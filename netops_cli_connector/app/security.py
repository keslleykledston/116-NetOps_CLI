from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse


def require_login(request: Request) -> None:
    if request.session.get("user"):
        return
    if request.url.path.startswith("/api/"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})


def redirect_after_login() -> RedirectResponse:
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
