#!/bin/bash

set -e

STAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/restore_document_lecture_link_$STAMP"
mkdir -p "$BACKUP_DIR"

backup_file() {
  if [ -f "$1" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$1")"
    cp "$1" "$BACKUP_DIR/$1"
    echo "Backed up $1"
  fi
}

echo "Backing up files..."
backup_file app/models/document.py
backup_file app/routes/documents.py
backup_file app/routes/lectures.py

echo "Updating app/models/document.py ..."
cat > app/models/document.py <<'EOF'
import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    lecture_id = Column(String, ForeignKey("lectures.id"), nullable=True)

    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)

    language = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    topic = Column(String, nullable=True)

    raw_text = Column(Text, nullable=True)
    processing_status = Column(String, nullable=True, default="ready")

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
EOF

echo "Patching SQLite schema to add lecture_id / processing_status if missing ..."
python - <<'PY'
import sqlite3
from pathlib import Path

db_candidates = [
    Path("learning_copilot.db"),
    Path("app.db"),
    Path("database.db"),
    Path("storage/app.db"),
]

db_path = None
for p in db_candidates:
    if p.exists():
        db_path = p
        break

if db_path is None:
    print("No sqlite DB file found in common locations. Skipping ALTER TABLE.")
else:
    print(f"Using DB: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(documents)")
    cols = [row[1] for row in cur.fetchall()]

    if "lecture_id" not in cols:
        cur.execute("ALTER TABLE documents ADD COLUMN lecture_id TEXT")
        print("Added documents.lecture_id")

    if "processing_status" not in cols:
        cur.execute("ALTER TABLE documents ADD COLUMN processing_status TEXT")
        cur.execute("UPDATE documents SET processing_status='ready' WHERE processing_status IS NULL")
        print("Added documents.processing_status")

    conn.commit()
    conn.close()
PY

echo "Updating app/routes/documents.py ..."
cat > app/routes/documents.py <<'EOF'
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
from app.models.lecture import Lecture

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
    lecture_id: Optional[str] = None


def _set_processing_status(document: Document, status: str):
    if hasattr(document, "processing_status"):
        setattr(document, "processing_status", status)


def _document_to_dict(doc: Document, lecture_title: Optional[str] = None):
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
    lecture_id: Optional[str],
    topic: Optional[str],
    source_type: Optional[str],
    file: UploadFile,
):
    file_extension = file.filename.split(".")[-1].lower()
    saved_file_path = os.path.join(UPLOAD_DIR, file.filename)

    new_document = Document(
        course_id=course_id,
        lecture_id=lecture_id,
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
            lecture_id=new_document.lecture_id,
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
            "lecture_id": new_document.lecture_id,
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
            "lecture_id": new_document.lecture_id,
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
EOF

echo "Updating app/routes/lectures.py ..."
cat > app/routes/lectures.py <<'EOF'
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lecture import Lecture
from app.models.lecturer import Lecturer
from app.models.document import Document
from app.models.summary import Summary
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/lectures", tags=["Lectures"])


class LectureCreate(BaseModel):
    course_id: str
    lecturer_id: Optional[str] = None
    title: str
    lecture_date: Optional[str] = None
    notes: Optional[str] = None


class LectureUpdate(BaseModel):
    lecturer_id: Optional[str] = None
    title: Optional[str] = None
    lecture_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/")
def create_lecture(payload: LectureCreate, db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Lecture title is required")

    lecture = Lecture(
        course_id=payload.course_id,
        lecturer_id=payload.lecturer_id,
        title=payload.title,
        lecture_date=payload.lecture_date,
        notes=payload.notes,
    )

    db.add(lecture)
    db.commit()
    db.refresh(lecture)

    lecturer_name = None
    if lecture.lecturer_id:
        lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()
        if lecturer:
            lecturer_name = lecturer.full_name

    return {
        "id": lecture.id,
        "course_id": lecture.course_id,
        "lecturer_id": lecture.lecturer_id,
        "lecturer_name": lecturer_name,
        "title": lecture.title,
        "lecture_date": lecture.lecture_date,
        "notes": lecture.notes,
    }


@router.get("/course/{course_id}")
def get_lectures_by_course(course_id: str, db: Session = Depends(get_db)):
    lectures = db.query(Lecture).filter(Lecture.course_id == course_id).all()

    result = []
    for lecture in lectures:
        lecturer_name = None
        if lecture.lecturer_id:
            lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()
            if lecturer:
                lecturer_name = lecturer.full_name

        result.append({
            "id": lecture.id,
            "course_id": lecture.course_id,
            "lecturer_id": lecture.lecturer_id,
            "lecturer_name": lecturer_name,
            "title": lecture.title,
            "lecture_date": lecture.lecture_date,
            "notes": lecture.notes,
        })

    return result


@router.put("/{lecture_id}")
def update_lecture(lecture_id: str, payload: LectureUpdate, db: Session = Depends(get_db)):
    lecture = db.query(Lecture).filter(Lecture.id == lecture_id).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    if payload.lecturer_id is not None:
        lecture.lecturer_id = payload.lecturer_id

    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Lecture title cannot be empty")
        lecture.title = payload.title

    if payload.lecture_date is not None:
        lecture.lecture_date = payload.lecture_date

    if payload.notes is not None:
        lecture.notes = payload.notes

    db.commit()
    db.refresh(lecture)

    lecturer_name = None
    if lecture.lecturer_id:
        lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()
        if lecturer:
            lecturer_name = lecturer.full_name

    return {
        "id": lecture.id,
        "course_id": lecture.course_id,
        "lecturer_id": lecture.lecturer_id,
        "lecturer_name": lecturer_name,
        "title": lecture.title,
        "lecture_date": lecture.lecture_date,
        "notes": lecture.notes,
    }


@router.delete("/{lecture_id}")
def delete_lecture(lecture_id: str, db: Session = Depends(get_db)):
    lecture = db.query(Lecture).filter(Lecture.id == lecture_id).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    documents = db.query(Document).filter(Document.lecture_id == lecture_id).all()
    vector_store = VectorStoreService()

    for doc in documents:
        db.query(Summary).filter(Summary.document_id == doc.id).delete(synchronize_session=False)
        vector_store.delete_by_document_id(doc.id)
        db.delete(doc)

    db.delete(lecture)
    db.commit()

    return {
        "status": "deleted",
        "deleted_lecture_id": lecture_id,
        "deleted_documents_count": len(documents),
    }
EOF

echo "Done."
echo "Now restart backend with:"
echo "uvicorn app.main:app --reload"
