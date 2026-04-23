"""
Thin helpers for consistent API response envelopes.

Success:  {"status": "success", "data": ..., "message": "..."}
Error:    {"status": "error",   "message": "...", "detail": ...}
Paginated: success envelope + {"pagination": {total, page, page_size, pages}}

These helpers are opt-in. Existing endpoints that return plain dicts are
still valid — adopt the envelope gradually as endpoints are touched.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi.responses import JSONResponse


def success(data: Any = None, message: str = "OK") -> dict:
    """
    Return a success envelope as a plain dict.

    HTTP status code is controlled by the @router decorator (e.g. status_code=201),
    not by this function — FastAPI ignores status_code inside a plain dict return.
    """
    return {"status": "success", "message": message, "data": data}


def paginated(
    items: list,
    total: int,
    page: int,
    page_size: int,
    message: str = "OK",
) -> dict:
    return {
        "status": "success",
        "message": message,
        "data": items,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": math.ceil(total / page_size) if page_size else 1,
        },
    }


def error(message: str, detail: Any = None, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message, "detail": detail},
    )
