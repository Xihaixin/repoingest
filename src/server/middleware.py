"""Request logging middleware for request-level tracing.

Every HTTP request is assigned a unique ``request_id`` which is bound into the
Loguru context for the whole request lifecycle (routing, parsing, cloning,
ingestion, response).  This lets a single failed request be traced end-to-end
across all log lines, and the identifier is echoed back to the client in the
``X-Request-ID`` response header so it can be reported for investigation.
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from gitingest.utils.logger import get_logger

logger = get_logger("server.middleware")


def _client_ip(request: Request) -> str:
    """Return the best-effort client IP, honoring ``X-Forwarded-For`` behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assign a ``request_id`` to every request and log its lifecycle.

    The request identifier and client metadata are bound into the Loguru
    context so every log line emitted while handling the request is tagged
    with them, enabling end-to-end tracing of a single request.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = uuid.uuid4().hex[:12]
        client_ip = _client_ip(request)

        with logger.contextualize(
            request_id=request_id,
            client_ip=client_ip,
            method=request.method,
            path=request.url.path,
        ):
            logger.debug("Request started")
            start = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("Unhandled exception while handling request")
                raise

            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Request completed | status={} | duration={:.1f}ms",
                response.status_code,
                duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
            return response
