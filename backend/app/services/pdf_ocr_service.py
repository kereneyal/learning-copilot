"""
PDF ingestion extraction: usable text layer when present; for scanned / image-heavy PDFs,
rasterized pages + Tesseract OCR is the primary recovery path, then optional vision fallback.

OCR requires the `pytesseract` binding, Pillow, and a working `tesseract` binary on PATH.
Those are expected to be installed and configured outside this application (no runtime installs).
"""
from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

OCR_DPI = int(os.getenv("PDF_OCR_DPI", "200"))


@dataclass
class PdfExtractionResult:
    text: str
    provider: str  # pdf_text | pdf_ocr | pdf_vision | none
    pages_processed: int
    ocr_used: bool


def normalize_pdf_text(raw: str) -> str:
    if not raw:
        return ""
    t = raw.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def is_usable_extracted_text(text: str, page_count: int = 1) -> bool:
    """
    Heuristic: reject empty, very short, or trivially small letter counts.
    For multi-page PDFs, expect more total content when page_count is high.
    """
    t = (text or "").strip()
    if not t:
        return False
    letters = sum(1 for c in t if c.isalpha() or ("\u0590" <= c <= "\u05FF"))
    min_letters = max(15, 8 * max(1, min(page_count, 8)))
    if letters < min_letters:
        return False
    min_len = max(40, 20 * max(1, page_count // 2))
    if len(t) < min_len:
        return False
    return True


def _analyze_pdf_pages(file_path: str) -> Tuple[str, int, bool]:
    """Return (joined text layer, page_count, image_heavy_flag)."""
    doc = fitz.open(file_path)
    try:
        n = len(doc)
        parts: List[str] = []
        weak_image_pages = 0
        for page in doc:
            raw = page.get_text() or ""
            parts.append(raw)
            tlen = len(raw.strip())
            try:
                n_imgs = len(page.get_images(full=True) or [])
            except Exception:
                n_imgs = 0
            if tlen < 30 and n_imgs > 0:
                weak_image_pages += 1
        full = "\n".join(parts)
        image_heavy = n > 0 and weak_image_pages >= max(1, (n + 1) // 2)
        return full, n, image_heavy
    finally:
        doc.close()


def ocr_stack_ready() -> Tuple[bool, str]:
    """
    Availability check for the OCR path (pytesseract import + Tesseract binary).
    Returns (True, "") when OCR can run; otherwise (False, short reason for logs).
    """
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as e:
        return False, f"OCR Python deps missing (pytesseract/Pillow): {e}"

    import pytesseract

    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        return False, f"Tesseract binary not usable (PATH or install): {e}"
    return True, ""


def _ocr_pdf_pages_pymupdf(file_path: str) -> Tuple[str, int]:
    """Render each page to bitmap and OCR. Returns (text, pages_processed)."""
    import pytesseract
    from PIL import Image

    doc = fitz.open(file_path)
    try:
        page_texts: List[str] = []
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
            png = pix.tobytes("png")
            img = Image.open(io.BytesIO(png))
            try:
                chunk = pytesseract.image_to_string(img, lang="heb+eng")
            except Exception:
                try:
                    chunk = pytesseract.image_to_string(img, lang="eng")
                except Exception as e:
                    logger.warning("pdf_ocr: tesseract page %s failed: %s", i + 1, e)
                    chunk = ""
            page_texts.append(chunk or "")
        combined = normalize_pdf_text("\n\n".join(page_texts))
        return combined, len(doc)
    finally:
        doc.close()


def extract_pdf_for_ingestion(file_path: str) -> PdfExtractionResult:
    """
    Try text layer → OCR (if needed) → vision fallback (see pdf_vision_fallback_service).
    """
    from app.services.pdf_vision_fallback_service import extract_pdf_text_via_vision

    logger.info("pdf_extraction: text_layer started path=%s", file_path)
    text_layer, n_pages, image_heavy = _analyze_pdf_pages(file_path)
    text_layer_norm = normalize_pdf_text(text_layer)
    text_usable = is_usable_extracted_text(text_layer_norm, n_pages)

    need_ocr = (not text_usable) or (
        image_heavy and len(text_layer_norm.strip()) < 500
    )

    if not need_ocr:
        logger.info(
            "pdf_extraction: text_layer succeeded pages=%s provider=pdf_text",
            n_pages,
        )
        return PdfExtractionResult(
            text=text_layer_norm,
            provider="pdf_text",
            pages_processed=n_pages,
            ocr_used=False,
        )

    logger.info(
        "pdf_extraction: scanned_or_weak_pdf pages=%s image_heavy=%s text_usable=%s — "
        "trying OCR first (primary path for scanned PDFs)",
        n_pages,
        image_heavy,
        text_usable,
    )

    ocr_ok, ocr_reason = ocr_stack_ready()
    if ocr_ok:
        try:
            ocr_text, ocr_pages = _ocr_pdf_pages_pymupdf(file_path)
            if is_usable_extracted_text(ocr_text, ocr_pages):
                logger.info(
                    "pdf_extraction: OCR succeeded pages=%s provider=pdf_ocr",
                    ocr_pages,
                )
                return PdfExtractionResult(
                    text=ocr_text,
                    provider="pdf_ocr",
                    pages_processed=ocr_pages,
                    ocr_used=True,
                )
            logger.warning(
                "pdf_extraction: OCR completed but text unusable pages=%s len=%s",
                ocr_pages,
                len(ocr_text or ""),
            )
        except Exception as e:
            logger.warning(
                "pdf_extraction: OCR raised exception; will try vision if configured: %s",
                e,
            )
    else:
        logger.warning(
            "pdf_extraction: OCR not available (%s); falling back to vision if configured",
            ocr_reason,
        )

    logger.info(
        "pdf_extraction: vision_fallback_after_ocr path=%s reason=ocr_unavailable_or_weak",
        file_path,
    )
    vision_text, vision_err, v_pages = extract_pdf_text_via_vision(file_path)
    if vision_err:
        logger.warning("pdf_extraction: vision API or model error: %s", vision_err)
    if vision_text and is_usable_extracted_text(vision_text, max(1, v_pages)):
        logger.info(
            "pdf_extraction: vision succeeded pages=%s provider=pdf_vision (after OCR missing/weak)",
            v_pages,
        )
        return PdfExtractionResult(
            text=normalize_pdf_text(vision_text),
            provider="pdf_vision",
            pages_processed=v_pages,
            ocr_used=True,
        )

    logger.error(
        "pdf_extraction: extraction_failed path=%s pages=%s detail=text_layer_weak "
        "and_OCR_unavailable_or_failed_and_vision_unusable",
        file_path,
        n_pages,
    )
    return PdfExtractionResult(
        text="",
        provider="none",
        pages_processed=n_pages,
        ocr_used=False,
    )
