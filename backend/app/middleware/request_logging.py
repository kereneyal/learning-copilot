import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Paths that generate noise in logs with no operational value.
_SILENT_PATHS = frozenset({"/health", "/", "/favicon.ico"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request/response with timing and a per-request trace ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SILENT_PATHS:
            return await call_next(request)

        request_id = uuid.uuid4().hex[:8]
        t0 = time.monotonic()

        logger.info(
            "http.request request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http.unhandled_error request_id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
            )
            raise

        duration_ms = int((time.monotonic() - t0) * 1000)
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        logger.log(
            level,
            "http.response request_id=%s method=%s path=%s status=%d duration_ms=%d",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response
