import os
import shutil
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap

from app.agents.ingestion_agent import IngestionAgent
from app.agents.chunking_agent import ChunkingAgent
from app.agents.summary_agent import SummaryAgent
from app.agents.course_summary_agent import CourseSummaryAgent
from app.agents.knowledge_map_agent import KnowledgeMapAgent
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class DocumentUpdate(BaseModel):
    file_name: Optional[str] = None
    topic: Optional[str] = None
    source_type: Optional[str] = None


def _set_processing_status(document: Document, status: str):
    if hasattr(document, "processing_status"):
        setattr(document, "processing_status", status)


def _document_to_dict(doc: Document):
    return {
        "id": doc.id,
        "course_id": doc.course_id,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "language": doc.language,
        "topic": doc.topic,
        "source_type": doc.source_type,
        "uploaded_at": getattr(doc, "uploaded_at", None),
        "processing_status": getattr(doc, "processing_status", "ready"),
    }


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


def _process_single_upload(
    db: Session,
    course_id: str,
    topic: Optional[str],
    source_type: Optional[str],
    file: UploadFile,
):
    file_extension = file.filename.split(".")[-1].lower()
    saved_file_path = os.path.join(UPLOAD_DIR, file.filename)

    new_document = Document(
        course_id=course_id,
        file_name=file.filename,
        file_path=saved_file_path,
        file_type=file_extension,
        language=None,
        source_type=source_type,
        topic=topic,
        raw_text=None,
    )

    _set_processing_status(new_document, "processing")

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        ingestion_agent = IngestionAgent()
        extracted_text = ingestion_agent.extract_text(saved_file_path, file_extension)
        detected_language = ingestion_agent.detect_language(extracted_text)

        chunking_agent = ChunkingAgent(max_chunk_size=1200, overlap_size=200)
        chunks = chunking_agent.chunk_text(extracted_text)

        new_document.language = detected_language
        new_document.raw_text = extracted_text
        _set_processing_status(new_document, "ready")
        db.commit()
        db.refresh(new_document)

        vector_store = VectorStoreService()
        vector_store.add_chunks(
            document_id=new_document.id,
            course_id=new_document.course_id,
            lecture_id=None,
            chunks=chunks,
        )

        summary_agent = SummaryAgent()
        summary_text = summary_agent.summarize(
            new_document.raw_text or "",
            new_document.language or "en"
        )

        new_summary = Summary(
            document_id=new_document.id,
            summary_text=summary_text,
            language=new_document.language
        )
        db.add(new_summary)
        db.commit()

        _refresh_course_aggregates(
            db=db,
            course_id=course_id,
            language=new_document.language or "en"
        )

        return {
            "id": new_document.id,
            "course_id": new_document.course_id,
            "file_name": new_document.file_name,
            "file_type": new_document.file_type,
            "language": new_document.language,
            "topic": new_document.topic,
            "source_type": new_document.source_type,
            "chunks_count": len(chunks),
            "processing_status": getattr(new_document, "processing_status", "ready"),
            "raw_text_preview": (extracted_text or "")[:500],
        }

    except Exception as e:
        _set_processing_status(new_document, "failed")
        db.commit()

        return {
            "id": new_document.id,
            "course_id": new_document.course_id,
            "file_name": new_document.file_name,
            "file_type": new_document.file_type,
            "language": getattr(new_document, "language", None),
            "topic": new_document.topic,
            "source_type": new_document.source_type,
            "processing_status": getattr(new_document, "processing_status", "failed"),
            "error": str(e),
        }


@router.post("/upload")
def upload_document(
    course_id: str = Form(...),
    topic: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return _process_single_upload(
        db=db,
        course_id=course_id,
        topic=topic,
        source_type=source_type,
        file=file,
    )


@router.post("/upload-multiple")
def upload_multiple_documents(
    course_id: str = Form(...),
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
            topic=topic,
            source_type=source_type,
            file=file,
        )
        results.append(result)

    return {
        "uploaded_count": len(results),
        "results": results
    }


@router.get("/course/{course_id}")
def get_documents_by_course(course_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.course_id == course_id).all()
    return [_document_to_dict(doc) for doc in documents]


@router.get("/lecture/{lecture_id}")
def get_documents_by_lecture(lecture_id: str, db: Session = Depends(get_db)):
    # כרגע המודל Document לא כולל lecture_id
    # לכן אין שיוך מסמכים ברמת הרצאה
    return []


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

    db.commit()
    db.refresh(doc)

    return _document_to_dict(doc)


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
