import logging
import os
import time
from typing import Optional

import chromadb
import requests as _requests
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db

router = APIRouter(prefix="/health", tags=["Health"])
logger = logging.getLogger(__name__)

# Module-level singleton so every health poll reuses the same ChromaDB client
# instead of allocating (and potentially file-locking) a new one each call.
_chroma_client: Optional[chromadb.ClientAPI] = None


def _get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        chroma_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")
        _chroma_client = chromadb.PersistentClient(path=chroma_path)
    return _chroma_client


@router.get(
    "",
    summary="Health check",
    description=(
        "Returns 200 when all critical components (database, vector store) are reachable. "
        "Returns 503 when any critical component is down. "
        "Ollama being unavailable is non-critical — it degrades to a warning."
    ),
)
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    checks: dict = {}
    t0 = time.monotonic()

    # ── Database ───────────────────────────────────────────────────────────────
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        logger.error("health.database_error error=%s", exc)
        checks["database"] = {"status": "error", "detail": str(exc)}

    # ── ChromaDB ───────────────────────────────────────────────────────────────
    try:
        _get_chroma_client().heartbeat()
        checks["chromadb"] = {"status": "ok"}
    except Exception as exc:
        logger.error("health.chromadb_error error=%s", exc)
        # Reset so the next call retries initialisation (handles restart recovery).
        _chroma_client = None
        checks["chromadb"] = {"status": "error", "detail": str(exc)}

    # ── Ollama (non-critical — may be replaced by OpenAI) ─────────────────────
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        resp = _requests.get(f"{ollama_url}/api/tags", timeout=3)
        resp.raise_for_status()
        checks["ollama"] = {"status": "ok"}
    except Exception as exc:
        checks["ollama"] = {"status": "unavailable", "detail": str(exc)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    critical_ok = all(
        checks[k]["status"] == "ok" for k in ("database", "chromadb") if k in checks
    )
    overall = "ok" if critical_ok else "degraded"

    return JSONResponse(
        status_code=200 if critical_ok else 503,
        content={
            "status": overall,
            "duration_ms": duration_ms,
            "checks": checks,
        },
    )
