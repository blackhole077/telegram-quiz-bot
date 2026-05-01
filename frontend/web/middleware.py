"""Request logging middleware."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        start = time.perf_counter()
        exc_type = None
        response = None
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            exc_type = type(exc).__name__
            raise
        finally:
            elapsed = round((time.perf_counter() - start) * 1000)
            status_code = getattr(response, "status_code", 500)
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=elapsed,
                request_id=request_id,
                error=exc_type,
            )
