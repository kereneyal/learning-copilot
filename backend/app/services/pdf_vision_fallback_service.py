"""
Vision-based PDF page text extraction (fallback when text layer + OCR fail).

Uses OpenAI vision; respects OPENAI_API_KEY and PDF_VISION_MAX_PAGES (default 10).
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional, Tuple

import fitz

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)

_VISION_MODEL = os.getenv("QUESTION_IMAGE_VISION_MODEL", "gpt-4o-mini")
_MAX_PAGES = int(os.getenv("PDF_VISION_MAX_PAGES", "10"))
_RENDER_DPI = int(os.getenv("PDF_VISION_RENDER_DPI", "150"))


def _vision_single_page_png(png_bytes: bytes, page_num: int) -> Tuple[Optional[str], Optional[str]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None, "OPENAI_API_KEY missing or OpenAI client unavailable"

    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        return None, str(e)

    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

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
                                f"This is PDF page {page_num}. Extract all visible text verbatim. "
                                "Preserve Hebrew and Latin, numbers, and line breaks. "
                                "Output only the page text, no commentary."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            max_tokens=4096,
        )
    except Exception as e:
        logger.warning("pdf_vision: API error page=%s model=%s: %s", page_num, _VISION_MODEL, e)
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

    return (raw if raw else None), None


def extract_pdf_text_via_vision(file_path: str) -> Tuple[str, Optional[str], int]:
    """
    Returns (combined_text, error_or_none, pages_processed).

    Logs a warning when the document is longer than PDF_VISION_MAX_PAGES so
    operators can detect silent content truncation.
    """
    doc = fitz.open(file_path)
    try:
        total_pages = len(doc)
        to_render = min(total_pages, max(1, _MAX_PAGES))

        # FIX: log truncation explicitly so missing content is never silent.
        if total_pages > to_render:
            logger.warning(
                "pdf_vision.truncated path=%s total_pages=%d max_pages=%d processing=%d "
                "— pages %d-%d will NOT be indexed; increase PDF_VISION_MAX_PAGES to cover them",
                file_path,
                total_pages,
                _MAX_PAGES,
                to_render,
                to_render + 1,
                total_pages,
            )
        else:
            logger.info(
                "pdf_vision.start path=%s total_pages=%d to_render=%d model=%s dpi=%d",
                file_path,
                total_pages,
                to_render,
                _VISION_MODEL,
                _RENDER_DPI,
            )

        parts: list[str] = []
        last_err: Optional[str] = None
        successful_pages = 0
        failed_pages = 0

        for i in range(to_render):
            page = doc[i]
            pix = page.get_pixmap(dpi=_RENDER_DPI, alpha=False)
            png = pix.tobytes("png")

            txt, err = _vision_single_page_png(png, i + 1)
            if err:
                last_err = err
                failed_pages += 1
                logger.debug(
                    "pdf_vision.page_failed page=%d/%d error=%s", i + 1, to_render, err
                )
            elif txt:
                parts.append(txt)
                successful_pages += 1
                logger.debug(
                    "pdf_vision.page_ok page=%d/%d chars=%d",
                    i + 1,
                    to_render,
                    len(txt),
                )
            else:
                # API returned success but empty text (blank page, pure image, etc.).
                failed_pages += 1
                logger.debug(
                    "pdf_vision.page_empty page=%d/%d", i + 1, to_render
                )

        combined = "\n\n".join(parts).strip()

        logger.info(
            "pdf_vision.done path=%s total_pages=%d rendered=%d successful=%d failed=%d "
            "combined_chars=%d truncated=%s",
            file_path,
            total_pages,
            to_render,
            successful_pages,
            failed_pages,
            len(combined),
            total_pages > to_render,
        )

        if not combined:
            return "", last_err or "vision produced no text", to_render

        return combined, None, to_render
    finally:
        doc.close()
