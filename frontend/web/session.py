"""Session ID helpers for web routers."""

from __future__ import annotations

import uuid

from fastapi import Request, Response


def get_session_id(request: Request) -> tuple[str, bool]:
    """Return (session_id, is_new). Never modifies any Response object.

    Callers that need to set the cookie must call set_session_cookie() on the
    Response they are about to return. FastAPI does not propagate cookies set
    on its injected Response dependency when the route itself returns a
    Response subclass (HTMLResponse / TemplateResponse).
    """
    existing = request.cookies.get("session_id")
    if existing:
        return existing, False
    return str(uuid.uuid4()), True


def set_session_cookie(response: Response, session_id: str) -> None:
    """Attach the session cookie directly to the given response."""
    response.set_cookie("session_id", session_id, httponly=True, samesite="lax")


def read_session_id(request: Request) -> str:
    """Return the session ID from the cookie, or an empty string if absent."""
    return request.cookies.get("session_id", "")
