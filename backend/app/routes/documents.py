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
from app.services.vector_store import VectorStoreService
from app.services.media_extraction_service import (
    MediaExtractionService,
    is_media_file,
    get_media_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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


def _document_to_dict(doc: Document, lecture_title: Optional[str] = None):
    raw_text = doc.raw_text or ""

    summary_obj = None
    if hasattr(doc, "summary"):
        try:
            summary_obj = doc.summary
        except Exception:
            summary_obj = None

    has_summary = bool(summary_obj and getattr(summary_obj, "summary_text", None))
    summary_text = getattr(summary_obj, "summary_text", "") if summary_obj else ""
    summary_preview = (summary_text[:280] + "...") if summary_text and len(summary_text) > 280 else summary_text

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


def _refresh_course_aggregates(db: Session, course_id: str, language: str = "en"):
    all_summaries = (
        db.query(Summary)
        .join(Document, Summary.document_id == Document.id)
        .filter(Document.course_id == course_id)
        .all()
    )

    summaries_texts = [s.summary_text for s in all_summaries if s.summary_text]
    if not summaries_texts:
        return

    course_summary_agent = CourseSummaryAgent()
    course_summary_text = course_summary_agent.summarize_course(
        summaries_texts,
        language or "en"
    )

    cs = CourseSummary(
        course_id=course_id,
        summary_text=course_summary_text,
        language=language
    )
    db.add(cs)
    db.commit()

    km_agent = KnowledgeMapAgent()
    km_text = km_agent.generate_map(
        course_summary=course_summary_text,
        document_summaries=summaries_texts,
        language=language or "en"
    )

    km = KnowledgeMap(
        course_id=course_id,
        map_text=km_text,
        language=language
    )
    db.add(km)
    db.commit()


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

    extracted_text, detected_language = _run_with_timeout("extracting", _extract, timeout_s=60)
    logger.info("processing.stage_end doc_id=%s stage=extracting text_len=%s", doc.id, len(extracted_text or ""))

    if not (extracted_text or "").strip():
        raise ProcessingStageError(
            stage="extracting",
            error_type="no_extractable_text",
            message=f"No extractable text (file_type={file_extension}). This file may be scanned/empty/unsupported.",
            retriable=False,
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

    doc.language = detected_language
    doc.raw_text = extracted_text
    _set_last_error(doc, None)
    db.commit()
    db.refresh(doc)

    _update_processing_state(db, doc, "embedding", 70)
    logger.info("processing.stage_start doc_id=%s stage=embedding", doc.id)

    vector_store = VectorStoreService()

    def _embed_and_write():
        try:
            vector_store.delete_by_document_id(doc.id)
        except Exception:
            pass
        return vector_store.add_chunks(
            document_id=doc.id,
            course_id=doc.course_id,
            lecture_id=getattr(doc, "lecture_id", None),
            chunks=chunks,
            embed_attempts=3,
            write_attempts=3,
            stage_timeout_s=60,
        )

    added = _run_with_timeout("embedding", _embed_and_write, timeout_s=60)
    logger.info("processing.stage_end doc_id=%s stage=embedding indexed_chunks=%s", doc.id, added)

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

    summary_agent = SummaryAgent()
    summary_text = summary_agent.summarize(
        doc.raw_text or "",
        doc.language or "en"
    )

    new_summary = Summary(
        document_id=doc.id,
        summary_text=summary_text,
        language=doc.language
    )
    db.add(new_summary)
    db.commit()

    _update_processing_state(db, doc, "ready", 100)

    aggregate_warning = None
    try:
        _refresh_course_aggregates(
            db=db,
            course_id=doc.course_id,
            language=doc.language or "en"
        )
    except Exception as e:
        aggregate_warning = str(e)
        _set_last_error(doc, aggregate_warning)
        _update_processing_state(db, doc, "ready", 100)

    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "processing_status": getattr(doc, "processing_status", "ready"),
        "language": doc.language,
        "chunks_count": len(chunks),
        "raw_text_preview": (doc.raw_text or "")[:500],
        "summary_created": True,
        "last_error": aggregate_warning or getattr(doc, "last_error", None),
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
        # Keep existing contract field name and value: technical error string (frontend hides by default)
        "error": getattr(doc, "last_error", None),
        # Add structured fields (non-breaking additions)
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


@router.get("/course/{course_id}")
def get_documents_by_course(course_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.course_id == course_id).all()
    result = []

    for doc in documents:
        lecture_title = None
        if getattr(doc, "lecture_id", None):
            lecture = db.query(Lecture).filter(Lecture.id == doc.lecture_id).first()
            if lecture:
                lecture_title = lecture.title

        result.append(_document_to_dict(doc, lecture_title=lecture_title))

    return result


@router.get("/lecture/{lecture_id}")
def get_documents_by_lecture(lecture_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.lecture_id == lecture_id).all()
    result = []

    for doc in documents:
        lecture_title = None
        if getattr(doc, "lecture_id", None):
            lecture = db.query(Lecture).filter(Lecture.id == doc.lecture_id).first()
            if lecture:
                lecture_title = lecture.title

        result.append(_document_to_dict(doc, lecture_title=lecture_title))

    return result


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

    return _document_to_dict(doc, lecture_title=lecture_title)


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
