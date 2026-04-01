"""
Extract question text from an uploaded image and run multiple-choice parsing.

Uses OpenAI vision when OPENAI_API_KEY is set; otherwise returns a clear error.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from app.services.multiple_choice_parser import parse_multiple_choice

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_VISION_MODEL = os.getenv("QUESTION_IMAGE_VISION_MODEL", "gpt-4o-mini")


def normalize_question_text(raw: str) -> str:
    if not raw:
        return ""
    t = raw.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _mime_for_filename(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/png")


def _extract_text_openai_vision(file_bytes: bytes, filename: str) -> tuple[Optional[str], Optional[str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None, "OPENAI_API_KEY is not set or OpenAI client unavailable; image extraction disabled"

    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:  # pragma: no cover
        return None, f"OpenAI client init failed: {e}"

    mime = _mime_for_filename(filename)
    b64 = base64.standard_b64encode(file_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    try:
        response = client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all visible text from this image verbatim. "
                                "Preserve Hebrew and Latin characters, numbering such as א. or A., "
                                "and line breaks where they appear. Output only the extracted text, "
                                "no commentary or translation."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            max_tokens=4096,
        )
    except Exception as e:
        logger.warning("question_image_extractor: vision API error: %s", e)
        return None, str(e)

    choice = response.choices[0] if response.choices else None
    msg = choice.message if choice else None
    raw = (getattr(msg, "content", None) or "").strip()
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        raw = "".join(parts).strip()

    if not raw:
        return None, "Vision model returned empty text"

    return raw, None


def extract_question_from_image(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Returns:
        success: bool
        raw_text: str (empty if failed)
        normalized_text: str
        parsed_multiple_choice: dict | None
        qa_mode: "multiple_choice" | "open"
        error: str | None
    """
    if len(file_bytes) > MAX_IMAGE_BYTES:
        return {
            "success": False,
            "raw_text": "",
            "normalized_text": "",
            "parsed_multiple_choice": None,
            "qa_mode": "open",
            "error": f"Image too large (max {MAX_IMAGE_BYTES} bytes)",
        }

    ext = Path(filename or "").suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return {
            "success": False,
            "raw_text": "",
            "normalized_text": "",
            "parsed_multiple_choice": None,
            "qa_mode": "open",
            "error": f"Unsupported image type {ext or '(none)'}; allowed: {sorted(IMAGE_EXTENSIONS)}",
        }

    raw_text, err = _extract_text_openai_vision(file_bytes, filename)
    if err:
        return {
            "success": False,
            "raw_text": "",
            "normalized_text": "",
            "parsed_multiple_choice": None,
            "qa_mode": "open",
            "error": err,
        }

    normalized = normalize_question_text(raw_text)
    parsed = parse_multiple_choice(normalized)
    qa_mode = "multiple_choice" if parsed else "open"

    logger.info(
        "question_image_extractor: extracted chars=%d qa_mode=%s mc_options=%s",
        len(normalized),
        qa_mode,
        len(parsed["options"]) if parsed else 0,
    )

    return {
        "success": True,
        "raw_text": raw_text,
        "normalized_text": normalized,
        "parsed_multiple_choice": parsed,
        "qa_mode": qa_mode,
        "error": None,
    }
