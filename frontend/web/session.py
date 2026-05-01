"""Session ID helpers for web routers."""

from __future__ import annotations

import uuid

from fastapi import Request, Response


def get_session_id(request: Request, response: Response) -> str:
    """Return the current session ID, setting a new cookie if none exists."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie("session_id", session_id, httponly=True, samesite="lax")
    return session_id


def read_session_id(request: Request) -> str:
    """Return the session ID from the cookie, or an empty string if absent."""
    return request.cookies.get("session_id", "")
