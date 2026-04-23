import os
import shutil
import threading
import json
import logging
import time
import concurrent.futures
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap
from app.models.lecture import Lecture

from app.agents.ingestion_agent import IngestionAgent
from app.agents.chunking_agent import ChunkingAgent
from app.agents.summary_agent import SummaryAgent
from app.agents.course_summary_agent import CourseSummaryAgent
from app.agents.knowledge_map_agent import KnowledgeMapAgent
from app.services.vector_store import (
    VectorStoreService,
    EmbeddingError,
    VectorStoreWriteError,
    _EMBED_SINGLE_TIMEOUT_S,
)
from app.services.media_extraction_service import (
    MediaExtractionService,
    is_media_file,
    get_media_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Upload validation constants ────────────────────────────────────────────────
# Override MAX_UPLOAD_MB via environment variable for large-lecture deployments.
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    # Documents
    "pdf", "docx", "doc", "pptx", "ppt",
    # Plain text
    "txt", "md",
    # Images (for vision pipeline)
    "png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp",
    # Video
    "mp4", "avi", "mov", "mkv", "wmv",
    # Audio
    "mp3", "wav", "m4a", "aac", "ogg",
})


class DocumentUpdate(BaseModel):
    file_name: Optional[str] = None
    topic: Optional[str] = None
    source_type: Optional[str] = None
    lecture_id: Optional[str] = None


def _set_processing_status(document: Document, status: str):
    if hasattr(document, "processing_status"):
        setattr(document, "processing_status", status)


def _set_processing_progress(document: Document, progress: int):
    if hasattr(document, "processing_progress"):
        try:
            current = getattr(document, "processing_progress", 0) or 0
            next_val = max(0, min(100, int(progress)))
            # progress must never decrease
            setattr(document, "processing_progress", max(int(current), next_val))
        except Exception:
            setattr(document, "processing_progress", 0)


def _set_last_error(document: Document, message: Optional[str]):
    if hasattr(document, "last_error"):
        setattr(document, "last_error", message)


def _set_error_fields(document: Document, error_type: Optional[str], error_stage: Optional[str]):
    if hasattr(document, "error_type"):
        setattr(document, "error_type", error_type)
    if hasattr(document, "error_stage"):
        setattr(document, "error_stage", error_stage)


def _document_to_dict(
    doc: Document,
    lecture_title: Optional[str] = None,
    summary: Optional["Summary"] = None,
):
    """
    Convert a Document ORM object to a response dict.

    Pass the pre-fetched Summary object (or None) explicitly — the Document
    model has no SQLAlchemy relationship named 'summary', so accessing
    doc.summary would always be None (dead code that was silently broken).
    """
    raw_text = doc.raw_text or ""
    summary_text = summary.summary_text if summary and summary.summary_text else ""
    has_summary = bool(summary_text.strip())
    summary_preview = (
        (summary_text[:280] + "...") if len(summary_text) > 280 else summary_text
    )

    return {
        "id": doc.id,
        "course_id": doc.course_id,
        "lecture_id": getattr(doc, "lecture_id", None),
        "lecture_title": lecture_title,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "language": doc.language,
        "topic": doc.topic,
        "source_type": doc.source_type,
        "uploaded_at": getattr(doc, "uploaded_at", None),
        "processing_status": getattr(doc, "processing_status", "ready"),
        "processing_progress": getattr(doc, "processing_progress", 0),
        "summary_status": getattr(doc, "summary_status", "not_started") or "not_started",
        "error_type": getattr(doc, "error_type", None),
        "error_stage": getattr(doc, "error_stage", None),
        "last_error": getattr(doc, "last_error", None),
        "has_summary": has_summary,
        "raw_text_length": len(raw_text),
        "summary_preview": summary_preview,
    }


def _update_processing_state(db: Session, doc: Document, status: str, progress: int):
    _set_processing_status(doc, status)
    _set_processing_progress(doc, progress)
    db.commit()
    db.refresh(doc)


class StageTimeoutError(Exception):
    def __init__(self, stage: str, timeout_s: int):
        super().__init__(f"Stage timeout: {stage} exceeded {timeout_s}s")
        self.stage = stage
        self.timeout_s = timeout_s


class ProcessingStageError(Exception):
    def __init__(self, stage: str, error_type: str, message: str, retriable: bool = False):
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.message = message
        self.retriable = retriable


def _run_with_timeout(stage: str, fn, timeout_s: int = 60):
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        try:
            return fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            raise StageTimeoutError(stage=stage, timeout_s=timeout_s)
        finally:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.info("stage.timing stage=%s elapsed_ms=%s", stage, elapsed_ms)


def _derive_error_fields(exc: Exception, fallback_stage: str):
    stage = fallback_stage
    if isinstance(exc, ProcessingStageError):
        stage = exc.stage or fallback_stage
    elif isinstance(exc, StageTimeoutError):
        stage = exc.stage or fallback_stage

    stage_norm = (stage or fallback_stage or "").lower()
    if stage_norm in {"extracting"}:
        return "extraction_error", "extracting"
    if stage_norm in {"chunking"}:
        return "chunking_error", "chunking"
    if stage_norm in {"embedding"}:
        return "embedding_error", "embedding"
    if stage_norm in {"indexing"}:
        return "indexing_error", "indexing"
    return "processing_error", stage_norm or "processing"


def _refresh_course_aggregates(
    db: Session,
    course_id: str,
    language: str = "en",
    doc_id: str = "?",
) -> None:
    """
    Rebuild course-level summary and knowledge map from all document summaries.

    Both steps (course summary, knowledge map) run independently — a failure
    in one does NOT prevent the other from running, and neither failure
    propagates to the caller.  The caller is itself inside a best-effort
    try/except in _run_summary_in_background.

    All failures are logged with full structured context so operators can
    diagnose which step failed, with what input size, on which provider.
    """
    t0 = time.time()

    all_summaries = (
        db.query(Summary)
        .join(Document, Summary.document_id == Document.id)
        .filter(Document.course_id == course_id)
        .all()
    )

    summaries_texts = [s.summary_text for s in all_summaries if s.summary_text]
    n = len(summaries_texts)

    if not summaries_texts:
        logger.info(
            "aggregates_refresh.skipped doc_id=%s course_id=%s reason=no_summaries",
            doc_id, course_id,
        )
        return

    provider = os.getenv(
        "AGGREGATES_PROVIDER",
        "openai" if os.getenv("OPENAI_API_KEY") else "ollama",
    )
    combined_chars = sum(len(s) for s in summaries_texts)
    logger.info(
        "aggregates_refresh.started doc_id=%s course_id=%s "
        "summary_count=%d total_input_chars=%d provider=%s",
        doc_id, course_id, n, combined_chars, provider,
    )

    # ------------------------------------------------------------------ #
    # Step 1 — course summary.  Failure is logged and skipped; step 2     #
    # still runs (with an empty course_summary_text as fallback input).   #
    # ------------------------------------------------------------------ #
    course_summary_text = ""
    t1 = time.time()
    try:
        logger.info(
            "aggregates_refresh.course_summary.started doc_id=%s course_id=%s "
            "summaries=%d provider=%s",
            doc_id, course_id, n, provider,
        )
        course_summary_agent = CourseSummaryAgent()
        course_summary_text = course_summary_agent.summarize_course(
            summaries_texts, language or "en"
        )
        db.add(CourseSummary(
            course_id=course_id,
            summary_text=course_summary_text,
            language=language,
        ))
        db.commit()
        logger.info(
            "aggregates_refresh.course_summary.completed doc_id=%s course_id=%s "
            "duration_ms=%d result_chars=%d",
            doc_id, course_id,
            int((time.time() - t1) * 1000),
            len(course_summary_text),
        )
    except Exception as exc:
        logger.warning(
            "aggregates_refresh.course_summary.failed doc_id=%s course_id=%s "
            "duration_ms=%d error=%s",
            doc_id, course_id,
            int((time.time() - t1) * 1000),
            exc,
        )
        # Continue — knowledge map step still runs even without a course summary.

    # ------------------------------------------------------------------ #
    # Step 2 — knowledge map.  Independent of step 1.                     #
    # ------------------------------------------------------------------ #
    t2 = time.time()
    try:
        logger.info(
            "aggregates_refresh.knowledge_map.started doc_id=%s course_id=%s "
            "summaries=%d course_summary_chars=%d provider=%s",
            doc_id, course_id, n, len(course_summary_text), provider,
        )
        km_agent = KnowledgeMapAgent()
        km_text = km_agent.generate_map(
            course_summary=course_summary_text,
            document_summaries=summaries_texts,
            language=language or "en",
        )
        db.add(KnowledgeMap(
            course_id=course_id,
            map_text=km_text,
            language=language,
        ))
        db.commit()
        logger.info(
            "aggregates_refresh.knowledge_map.completed doc_id=%s course_id=%s "
            "duration_ms=%d result_chars=%d",
            doc_id, course_id,
            int((time.time() - t2) * 1000),
            len(km_text),
        )
    except Exception as exc:
        logger.warning(
            "aggregates_refresh.knowledge_map.failed doc_id=%s course_id=%s "
            "duration_ms=%d error=%s",
            doc_id, course_id,
            int((time.time() - t2) * 1000),
            exc,
        )

    logger.info(
        "aggregates_refresh.completed doc_id=%s course_id=%s total_ms=%d",
        doc_id, course_id, int((time.time() - t0) * 1000),
    )


def _run_summary_in_background(document_id: str) -> None:
    """
    Best-effort summary generation in its own thread.

    The document is already marked 'ready' before this runs — summary
    completion or failure never changes processing_status.

    Ollama note: if summary_agent.summarize() raises Timeout the HTTP client
    stops waiting, but the Ollama generation goroutine keeps running until it
    finishes.  This is a known Ollama limitation; the document remains fully
    searchable and usable regardless.
    """
    thread_db = SessionLocal()
    t0 = time.time()
    try:
        doc = thread_db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("summary_job.doc_not_found doc_id=%s", document_id)
            return

        doc.summary_status = "generating"
        thread_db.commit()
        logger.info(
            "summary_job.started doc_id=%s provider=%s",
            document_id,
            os.getenv("SUMMARY_PROVIDER", "openai" if os.getenv("OPENAI_API_KEY") else "ollama"),
        )

        summary_agent = SummaryAgent()
        summary_text = summary_agent.summarize(doc.raw_text or "", doc.language or "en")

        thread_db.query(Summary).filter(
            Summary.document_id == document_id
        ).delete(synchronize_session=False)
        thread_db.add(Summary(
            document_id=document_id,
            summary_text=summary_text,
            language=doc.language,
        ))
        doc.summary_status = "completed"
        thread_db.commit()

        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            "summary_job.completed doc_id=%s elapsed_ms=%d summary_chars=%d",
            document_id,
            elapsed_ms,
            len(summary_text),
        )

        # Refresh course-level aggregates — best-effort, errors do NOT revert summary_status.
        # _refresh_course_aggregates isolates each step internally; this outer try/except
        # is a final safety net for unexpected failures (e.g. DB connection error).
        try:
            doc_fresh = thread_db.query(Document).filter(Document.id == document_id).first()
            if doc_fresh:
                _refresh_course_aggregates(
                    db=thread_db,
                    course_id=doc_fresh.course_id,
                    language=doc_fresh.language or "en",
                    doc_id=document_id,
                )
        except Exception as agg_exc:
            logger.warning(
                "summary_job.aggregates_unexpected_error doc_id=%s error=%s",
                document_id,
                agg_exc,
            )

    except Exception as exc:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "summary_job.failed doc_id=%s elapsed_ms=%d error=%s",
            document_id,
            elapsed_ms,
            exc,
        )
        try:
            doc_err = thread_db.query(Document).filter(Document.id == document_id).first()
            if doc_err:
                doc_err.summary_status = "failed"
                _set_last_error(doc_err, f"summary_failed: {exc}")
                thread_db.commit()
        except Exception as persist_exc:
            logger.warning(
                "summary_job.status_persist_failed doc_id=%s error=%s",
                document_id,
                persist_exc,
            )
    finally:
        thread_db.close()


def _process_existing_document(db: Session, doc: Document):
    if not getattr(doc, "file_path", None):
        raise Exception("Document has no file_path")

    if not os.path.exists(doc.file_path):
        raise Exception(f"File not found: {doc.file_path}")

    file_extension = (doc.file_type or doc.file_name.split(".")[-1].lower()) if doc.file_name else "txt"

    _set_last_error(doc, None)
    _set_error_fields(doc, None, None)
    _update_processing_state(db, doc, "extracting", 20)
    logger.info("processing.stage_start doc_id=%s stage=extracting", doc.id)

    ingestion_agent = IngestionAgent()
    media_service = MediaExtractionService()

    def _extract():
        if doc.file_name and is_media_file(doc.file_name):
            with open(doc.file_path, "rb") as f:
                file_bytes = f.read()

            media_result = media_service.transcribe_file(file_bytes, doc.file_name)

            if not media_result.get("success"):
                raise ProcessingStageError(
                    stage="extracting",
                    error_type="media_transcription_failed",
                    message=media_result.get("error") or "Media transcription failed",
                    retriable=True,
                )

            extracted_text_local = media_result.get("text", "") or ""
            detected_language_local = ingestion_agent.detect_language(extracted_text_local) if extracted_text_local else "en"

            if not getattr(doc, "source_type", None):
                doc.source_type = get_media_type(doc.file_name)

            return extracted_text_local, detected_language_local

        extracted_text_local = ingestion_agent.extract_text(doc.file_path, file_extension)
        detected_language_local = ingestion_agent.detect_language(extracted_text_local)
        return extracted_text_local, detected_language_local

    extract_timeout_s = 180 if (file_extension or "").lower() == "pdf" else 60
    extracted_text, detected_language = _run_with_timeout(
        "extracting", _extract, timeout_s=extract_timeout_s
    )
    logger.info("processing.stage_end doc_id=%s stage=extracting text_len=%s", doc.id, len(extracted_text or ""))
    pdf_meta = getattr(ingestion_agent, "last_pdf_meta", None)
    if (file_extension or "").lower() == "pdf" and pdf_meta:
        logger.info(
            "processing.pdf_extraction doc_id=%s final_provider=%s pages_processed=%s ocr_used=%s",
            doc.id,
            pdf_meta.get("provider"),
            pdf_meta.get("pages_processed"),
            pdf_meta.get("ocr_used"),
        )

    if not (extracted_text or "").strip():
        if (file_extension or "").lower() == "pdf":
            fail_msg = (
                "No extractable text (file_type=pdf). Text layer missing or too weak; "
                "OCR was unavailable or did not yield usable text; "
                "vision fallback did not yield usable text."
            )
        else:
            fail_msg = (
                f"No extractable text (file_type={file_extension}). "
                "This file may be scanned/empty/unsupported."
            )
        raise ProcessingStageError(
            stage="extracting",
            error_type="no_extractable_text",
            message=fail_msg,
            retriable=False,
        )

    # FIX: persist raw_text and language immediately after successful extraction,
    # BEFORE chunking begins.  Previously these were only saved after chunking
    # succeeded — a chunking failure would lose the extracted text entirely and
    # force a full re-extraction on retry (expensive for OCR/vision documents).
    doc.language = detected_language
    doc.raw_text = extracted_text
    _set_last_error(doc, None)
    db.commit()
    db.refresh(doc)
    logger.info(
        "processing.raw_text_saved doc_id=%s lang=%s text_len=%d",
        doc.id,
        detected_language,
        len(extracted_text),
    )

    _update_processing_state(db, doc, "chunking", 40)
    logger.info("processing.stage_start doc_id=%s stage=chunking", doc.id)

    def _chunk():
        chunking_agent = ChunkingAgent(max_chunk_size=1200, overlap_size=200)
        return chunking_agent.chunk_text(extracted_text)

    chunks = _run_with_timeout("chunking", _chunk, timeout_s=60)
    logger.info("processing.stage_end doc_id=%s stage=chunking chunks=%s", doc.id, len(chunks or []))

    if not chunks:
        raise ProcessingStageError(
            stage="chunking",
            error_type="no_chunks",
            message="Chunking produced 0 chunks; cannot index document for search.",
            retriable=False,
        )

    _update_processing_state(db, doc, "embedding", 70)
    logger.info(
        "processing.stage_start doc_id=%s stage=embedding chunks=%d embed_timeout_s=%d",
        doc.id,
        len(chunks),
        _EMBED_SINGLE_TIMEOUT_S,
    )

    # No stage-level timeout for embedding — per-request timeout (_EMBED_SINGLE_TIMEOUT_S)
    # is the only guard.  A slow CPU Ollama may take 2–3 minutes for a small file;
    # wrapping in a wall-clock timeout causes false "failed" status for valid uploads.
    vector_store = VectorStoreService()
    embed_t0 = time.time()
    try:
        try:
            vector_store.delete_by_document_id(doc.id)
        except Exception:
            pass

        added = vector_store.add_chunks(
            document_id=doc.id,
            course_id=doc.course_id,
            lecture_id=getattr(doc, "lecture_id", None),
            chunks=chunks,
            embed_attempts=3,
            write_attempts=3,
            embed_timeout_s=_EMBED_SINGLE_TIMEOUT_S,
        )
    except (EmbeddingError, VectorStoreWriteError) as exc:
        raise ProcessingStageError(
            stage="embedding",
            error_type="embedding_failed",
            message=str(exc),
            retriable=True,
        )
    except Exception as exc:
        raise ProcessingStageError(
            stage="embedding",
            error_type="embedding_failed",
            message=str(exc),
            retriable=True,
        )

    embed_elapsed_ms = int((time.time() - embed_t0) * 1000)
    logger.info(
        "processing.stage_end doc_id=%s stage=embedding indexed_chunks=%d elapsed_ms=%d",
        doc.id,
        added,
        embed_elapsed_ms,
    )

    if added <= 0:
        raise ProcessingStageError(
            stage="embedding",
            error_type="vector_store_empty_write",
            message="Vector store write produced 0 indexed chunks.",
            retriable=True,
        )

    _update_processing_state(db, doc, "indexing", 90)
    logger.info("processing.stage_start doc_id=%s stage=indexing", doc.id)

    def _indexing():
        db.query(Summary).filter(Summary.document_id == doc.id).delete(synchronize_session=False)
        db.commit()

    _run_with_timeout("indexing", _indexing, timeout_s=60)
    logger.info("processing.stage_end doc_id=%s stage=indexing", doc.id)

    # Mark document ready — searchable and usable for QA from this point on.
    _update_processing_state(db, doc, "ready", 100)
    doc.summary_status = "pending"
    db.commit()

    # Launch summary in a separate thread so ingestion returns immediately.
    # Summary completion/failure never affects processing_status.
    summary_thread = threading.Thread(
        target=_run_summary_in_background,
        args=(doc.id,),
        daemon=True,
    )
    summary_thread.start()
    logger.info("processing.summary_dispatched doc_id=%s", doc.id)

    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "processing_status": "ready",
        "summary_status": "pending",
        "language": doc.language,
        "chunks_count": len(chunks),
        "raw_text_preview": (doc.raw_text or "")[:500],
    }


def _process_single_upload(
    db: Session,
    course_id: str,
    lecture_id: Optional[str],
    topic: Optional[str],
    source_type: Optional[str],
    file: UploadFile,
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    safe_filename = os.path.basename(file.filename)
    file_extension = safe_filename.split(".")[-1].lower() if "." in safe_filename else "txt"

    # ── Validate before touching the database ─────────────────────────────────
    if file_extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '.{file_extension}'. "
                f"Allowed types: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
            ),
        )

    # Measure file size via seek so we never load the whole file into memory.
    # file.file is a SpooledTemporaryFile which supports seek even for large files.
    try:
        file.file.seek(0, 2)          # seek to end
        upload_size = file.file.tell()
        file.file.seek(0)             # reset to beginning for subsequent reads
    except Exception:
        upload_size = 0               # can't determine — allow through, disk will cap it

    if upload_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({upload_size // (1024 * 1024)} MB). "
                f"Maximum allowed size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            ),
        )

    new_document = Document(
        course_id=course_id,
        lecture_id=lecture_id,
        file_name=safe_filename,
        file_path="",
        file_type=file_extension,
        language=None,
        source_type=source_type,
        topic=topic,
        raw_text=None,
    )

    _set_processing_status(new_document, "processing")
    _set_processing_progress(new_document, 0)
    _set_last_error(new_document, None)

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    doc_dir = os.path.join(UPLOAD_DIR, new_document.id)
    os.makedirs(doc_dir, exist_ok=True)
    saved_file_path = os.path.join(doc_dir, safe_filename)

    new_document.file_path = saved_file_path
    db.commit()
    db.refresh(new_document)

    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        def _run_processing_in_thread(document_id: str):
            thread_db = SessionLocal()
            try:
                doc_in_thread = thread_db.query(Document).filter(Document.id == document_id).first()
                if not doc_in_thread:
                    return
                try:
                    _process_existing_document(thread_db, doc_in_thread)
                except Exception as e:
                    _set_processing_status(doc_in_thread, "failed")
                    error_type, error_stage = _derive_error_fields(
                        e,
                        fallback_stage=getattr(doc_in_thread, "processing_status", "processing") or "processing",
                    )
                    _set_error_fields(doc_in_thread, error_type, error_stage)
                    # Keep last_error as raw technical message for optional display.
                    _set_last_error(doc_in_thread, str(e))
                    thread_db.commit()
            finally:
                thread_db.close()

        t = threading.Thread(target=_run_processing_in_thread, args=(new_document.id,), daemon=True)
        t.start()

        # Return immediately; preserve existing response keys (placeholders)
        return {
            "id": new_document.id,
            "course_id": new_document.course_id,
            "lecture_id": new_document.lecture_id,
            "file_name": new_document.file_name,
            "file_type": new_document.file_type,
            "language": getattr(new_document, "language", None),
            "topic": new_document.topic,
            "source_type": new_document.source_type,
            "processing_status": getattr(new_document, "processing_status", "processing"),
            "processing_progress": getattr(new_document, "processing_progress", 0),
            "last_error": getattr(new_document, "last_error", None),
            "chunks_count": 0,
            "raw_text_preview": "",
            "summary_created": False,
        }

    except Exception as e:
        try:
            VectorStoreService().delete_by_document_id(new_document.id)
        except Exception:
            pass

        _set_processing_status(new_document, "failed")
        _set_last_error(new_document, str(e))
        db.commit()

        return {
            "id": new_document.id,
            "course_id": new_document.course_id,
            "lecture_id": new_document.lecture_id,
            "file_name": new_document.file_name,
            "file_type": new_document.file_type,
            "language": getattr(new_document, "language", None),
            "topic": new_document.topic,
            "source_type": new_document.source_type,
            "processing_status": getattr(new_document, "processing_status", "failed"),
            "error": str(e),
            "last_error": getattr(new_document, "last_error", None),
        }


@router.post("/upload")
def upload_document(
    course_id: str = Form(...),
    lecture_id: Optional[str] = Form(None),
    topic: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return _process_single_upload(
        db=db,
        course_id=course_id,
        lecture_id=lecture_id,
        topic=topic,
        source_type=source_type,
        file=file,
    )


@router.post("/upload-multiple")
def upload_multiple_documents(
    course_id: str = Form(...),
    lecture_id: Optional[str] = Form(None),
    topic: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    results = []

    for file in files:
        result = _process_single_upload(
            db=db,
            course_id=course_id,
            lecture_id=lecture_id,
            topic=topic,
            source_type=source_type,
            file=file,
        )
        results.append(result)

    return {
        "uploaded_count": len(results),
        "results": results
    }


@router.get("/{document_id}/status")
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "status": getattr(doc, "processing_status", "ready"),
        "progress": getattr(doc, "processing_progress", 0) or 0,
        "summary_status": getattr(doc, "summary_status", "not_started") or "not_started",
        "error": getattr(doc, "last_error", None),
        "error_type": getattr(doc, "error_type", None),
        "error_stage": getattr(doc, "error_stage", None),
    }


@router.post("/{document_id}/retry-processing")
def retry_processing(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        result = _process_existing_document(db, doc)
        return {
            "status": "retried",
            **result,
        }
    except Exception as e:
        _set_processing_status(doc, "failed")
        _set_last_error(doc, str(e))
        db.commit()
        raise HTTPException(status_code=500, detail=f"Retry processing failed: {str(e)}")


@router.post("/{document_id}/retry-summary")
def retry_summary(document_id: str, db: Session = Depends(get_db)):
    """
    Re-dispatch summary generation for a document that is already ready.
    Safe to call when summary_status is 'failed' or 'not_started'.
    Returns immediately; summary runs in a background thread.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not getattr(doc, "raw_text", None):
        raise HTTPException(
            status_code=400,
            detail="Document has no raw_text — run full processing first",
        )

    current = getattr(doc, "summary_status", "not_started") or "not_started"
    if current == "generating":
        return {"status": "already_generating", "summary_status": "generating"}

    doc.summary_status = "pending"
    _set_last_error(doc, None)
    db.commit()

    t = threading.Thread(
        target=_run_summary_in_background,
        args=(document_id,),
        daemon=True,
    )
    t.start()
    logger.info("summary_job.retry_dispatched doc_id=%s", document_id)
    return {"status": "dispatched", "summary_status": "pending"}


def _batch_lecture_titles(db: Session, lecture_ids) -> dict:
    """Return {lecture_id: title} for a collection of IDs in one query."""
    ids = [lid for lid in lecture_ids if lid]
    if not ids:
        return {}
    rows = db.query(Lecture.id, Lecture.title).filter(Lecture.id.in_(ids)).all()
    return {row.id: row.title for row in rows}


def _batch_summaries(db: Session, document_ids) -> dict:
    """Return {document_id: Summary} for a collection of doc IDs in one query."""
    ids = [did for did in document_ids if did]
    if not ids:
        return {}
    rows = db.query(Summary).filter(Summary.document_id.in_(ids)).all()
    # One summary per document; keep the first if duplicates exist.
    out = {}
    for row in rows:
        if row.document_id not in out:
            out[row.document_id] = row
    return out


@router.get("/course/{course_id}")
def get_documents_by_course(course_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.course_id == course_id).all()

    # FIX: single batch query for all lectures and summaries instead of N+1.
    lecture_titles = _batch_lecture_titles(db, (d.lecture_id for d in documents))
    summaries = _batch_summaries(db, (d.id for d in documents))

    return [
        _document_to_dict(
            doc,
            lecture_title=lecture_titles.get(doc.lecture_id),
            summary=summaries.get(doc.id),
        )
        for doc in documents
    ]


@router.get("/lecture/{lecture_id}")
def get_documents_by_lecture(lecture_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.lecture_id == lecture_id).all()

    # FIX: single batch query for all lectures and summaries instead of N+1.
    lecture_titles = _batch_lecture_titles(db, (d.lecture_id for d in documents))
    summaries = _batch_summaries(db, (d.id for d in documents))

    return [
        _document_to_dict(
            doc,
            lecture_title=lecture_titles.get(doc.lecture_id),
            summary=summaries.get(doc.id),
        )
        for doc in documents
    ]


@router.get("/{document_id}")
def get_document_details(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    lecture_title = None
    if getattr(doc, "lecture_id", None):
        lecture = db.query(Lecture).filter(Lecture.id == doc.lecture_id).first()
        if lecture:
            lecture_title = lecture.title

    summary = db.query(Summary).filter(Summary.document_id == document_id).first()

    raw_text = doc.raw_text or ""
    summary_text = summary.summary_text if summary else ""

    return {
        "id": doc.id,
        "course_id": doc.course_id,
        "lecture_id": getattr(doc, "lecture_id", None),
        "lecture_title": lecture_title,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "language": doc.language,
        "topic": doc.topic,
        "source_type": doc.source_type,
        "uploaded_at": getattr(doc, "uploaded_at", None),
        "processing_status": getattr(doc, "processing_status", "ready"),
        "processing_progress": getattr(doc, "processing_progress", 0),
        "summary_status": getattr(doc, "summary_status", "not_started") or "not_started",
        "last_error": getattr(doc, "last_error", None),
        "has_summary": bool(summary_text.strip()),
        "summary_text": summary_text,
        "raw_text_preview": raw_text[:3000],
        "raw_text_length": len(raw_text),
    }


@router.put("/{document_id}")
def update_document(document_id: str, payload: DocumentUpdate, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.file_name is not None:
        doc.file_name = payload.file_name
    if payload.topic is not None:
        doc.topic = payload.topic
    if payload.source_type is not None:
        doc.source_type = payload.source_type
    if payload.lecture_id is not None:
        doc.lecture_id = payload.lecture_id

    db.commit()
    db.refresh(doc)

    lecture_title = None
    if getattr(doc, "lecture_id", None):
        lecture = db.query(Lecture).filter(Lecture.id == doc.lecture_id).first()
        if lecture:
            lecture_title = lecture.title

    summary = db.query(Summary).filter(Summary.document_id == doc.id).first()
    return _document_to_dict(doc, lecture_title=lecture_title, summary=summary)


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    vector_store = VectorStoreService()
    db.query(Summary).filter(Summary.document_id == document_id).delete(synchronize_session=False)

    file_path = getattr(doc, "file_path", None)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    vector_store.delete_by_document_id(document_id)

    db.delete(doc)
    db.commit()

    return {
        "status": "deleted",
        "deleted_document_id": document_id
    }
