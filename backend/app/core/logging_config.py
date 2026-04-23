import json
import logging
import os
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a compact JSON line for structured log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """
    Call once at application startup.

    Reads LOG_LEVEL from the environment (default: INFO).
    In development (LOG_FORMAT=text) emits plain-text instead of JSON.
    """
    resolved_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    numeric = getattr(logging, resolved_level, logging.INFO)

    use_json = os.getenv("LOG_FORMAT", "json").lower() != "text"

    root = logging.getLogger()
    root.setLevel(numeric)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if use_json:
            handler.setFormatter(_JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
            )
        root.addHandler(handler)

    # Suppress noisy third-party loggers that don't add signal at INFO.
    for noisy in ("uvicorn.access", "httpx", "httpcore", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
