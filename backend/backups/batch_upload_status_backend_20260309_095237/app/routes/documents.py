import os
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.lecture import Lecture
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


@router.post("/upload")
def upload_document(
    course_id: str = Form(...),
    lecture_id: Optional[str] = Form(None),
    topic: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    file_extension = file.filename.split(".")[-1].lower()
    saved_file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion_agent = IngestionAgent()
    extracted_text = ingestion_agent.extract_text(saved_file_path, file_extension)
    detected_language = ingestion_agent.detect_language(extracted_text)

    chunking_agent = ChunkingAgent(max_chunk_size=1200, overlap_size=200)
    chunks = chunking_agent.chunk_text(extracted_text)

    new_document = Document(
        course_id=course_id,
        lecture_id=lecture_id,
        file_name=file.filename,
        file_path=saved_file_path,
        file_type=file_extension,
        language=detected_language,
        source_type=source_type,
        topic=topic,
        raw_text=extracted_text,
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    vector_store = VectorStoreService()
    vector_store.add_chunks(
        document_id=new_document.id,
        course_id=new_document.course_id,
        lecture_id=getattr(new_document, "lecture_id", None),
        chunks=chunks
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

    all_summaries = (
        db.query(Summary)
        .join(Document, Summary.document_id == Document.id)
        .filter(Document.course_id == course_id)
        .all()
    )

    summaries_texts = [s.summary_text for s in all_summaries if s.summary_text]

    if summaries_texts:
        course_summary_agent = CourseSummaryAgent()
        course_summary_text = course_summary_agent.summarize_course(
            summaries_texts,
            new_document.language or "en"
        )

        cs = CourseSummary(
            course_id=course_id,
            summary_text=course_summary_text,
            language=new_document.language
        )
        db.add(cs)
        db.commit()

        km_agent = KnowledgeMapAgent()
        km_text = km_agent.generate_map(
            course_summary=course_summary_text,
            document_summaries=summaries_texts,
            language=new_document.language or "en"
        )

        km = KnowledgeMap(
            course_id=course_id,
            map_text=km_text,
            language=new_document.language
        )
        db.add(km)
        db.commit()

    return {
        "id": new_document.id,
        "course_id": new_document.course_id,
        "lecture_id": getattr(new_document, "lecture_id", None),
        "file_name": new_document.file_name,
        "file_type": new_document.file_type,
        "language": new_document.language,
        "topic": new_document.topic,
        "source_type": new_document.source_type,
        "chunks_count": len(chunks),
        "raw_text_preview": extracted_text[:500],
    }


@router.get("/course/{course_id}")
def get_documents_by_course(course_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.course_id == course_id).all()

    result = []
    for doc in documents:
        lecture = None
        if getattr(doc, "lecture_id", None):
            lecture = db.query(Lecture).filter(Lecture.id == doc.lecture_id).first()

        result.append({
            "id": doc.id,
            "course_id": doc.course_id,
            "lecture_id": getattr(doc, "lecture_id", None),
            "lecture_title": lecture.title if lecture else None,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "language": doc.language,
            "topic": doc.topic,
            "source_type": doc.source_type,
            "uploaded_at": doc.uploaded_at,
        })

    return result


@router.get("/lecture/{lecture_id}")
def get_documents_by_lecture(lecture_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.lecture_id == lecture_id).all()

    return [
        {
            "id": doc.id,
            "course_id": doc.course_id,
            "lecture_id": getattr(doc, "lecture_id", None),
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "language": doc.language,
            "topic": doc.topic,
            "source_type": doc.source_type,
            "uploaded_at": doc.uploaded_at,
        }
        for doc in documents
    ]


@router.put("/{document_id}")
def update_document(document_id: str, payload: DocumentUpdate, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.file_name is not None and payload.file_name.strip():
        old_path = document.file_path
        new_path = old_path

        if old_path and os.path.exists(old_path):
            directory = os.path.dirname(old_path)
            new_path = os.path.join(directory, payload.file_name)
            try:
                os.rename(old_path, new_path)
            except Exception:
                new_path = old_path

        document.file_name = payload.file_name
        document.file_path = new_path

    if payload.topic is not None:
        document.topic = payload.topic

    if payload.source_type is not None:
        document.source_type = payload.source_type

    db.commit()
    db.refresh(document)

    return {
        "id": document.id,
        "course_id": document.course_id,
        "lecture_id": getattr(document, "lecture_id", None),
        "file_name": document.file_name,
        "file_type": document.file_type,
        "language": document.language,
        "topic": document.topic,
        "source_type": document.source_type,
        "uploaded_at": document.uploaded_at,
    }


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    vector_store = VectorStoreService()

    db.query(Summary).filter(Summary.document_id == document_id).delete(synchronize_session=False)
    vector_store.delete_by_document_id(document_id)

    file_path = document.file_path
    db.delete(document)
    db.commit()

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"file delete warning: {e}")

    return {
        "status": "deleted",
        "deleted_document_id": document_id
    }
