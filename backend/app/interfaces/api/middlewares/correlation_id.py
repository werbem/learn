"""Correlation ID middleware (skeleton)."""

from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Attaches a unique correlation ID to every request/response."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        cid = request.headers.get("X-Correlation-ID", str(uuid4()))
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
