#!/bin/bash

set -e

mkdir -p app/utils
mkdir -p app/models
mkdir -p app/routes

echo "Writing language utils..."
cat > app/utils/language_utils.py <<'EOF'
def detect_text_language(text: str) -> str:
    if not text:
        return "en"

    hebrew_chars = sum(1 for ch in text if '\u0590' <= ch <= '\u05FF')
    english_chars = sum(1 for ch in text if ('a' <= ch.lower() <= 'z'))

    if hebrew_chars > english_chars:
        return "he"
    return "en"
EOF

echo "Writing lecturer model..."
cat > app/models/lecturer.py <<'EOF'
from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class Lecturer(Base):
    __tablename__ = "lecturers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String, nullable=False)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
EOF

echo "Writing lecture model..."
cat > app/models/lecture.py <<'EOF'
from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class Lecture(Base):
    __tablename__ = "lectures"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    lecturer_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    lecture_date = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
EOF

echo "Writing lecturers route..."
cat > app/routes/lecturers.py <<'EOF'
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lecturer import Lecturer

router = APIRouter(prefix="/lecturers", tags=["Lecturers"])


class LecturerCreate(BaseModel):
    full_name: str
    bio: Optional[str] = None


@router.post("/")
def create_lecturer(payload: LecturerCreate, db: Session = Depends(get_db)):
    lecturer = Lecturer(
        full_name=payload.full_name,
        bio=payload.bio
    )
    db.add(lecturer)
    db.commit()
    db.refresh(lecturer)

    return {
        "id": lecturer.id,
        "full_name": lecturer.full_name,
        "bio": lecturer.bio,
        "created_at": lecturer.created_at,
    }


@router.get("/")
def list_lecturers(db: Session = Depends(get_db)):
    lecturers = db.query(Lecturer).all()

    return [
        {
            "id": lecturer.id,
            "full_name": lecturer.full_name,
            "bio": lecturer.bio,
            "created_at": lecturer.created_at,
        }
        for lecturer in lecturers
    ]
EOF

echo "Writing lectures route..."
cat > app/routes/lectures.py <<'EOF'
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lecture import Lecture
from app.models.lecturer import Lecturer

router = APIRouter(prefix="/lectures", tags=["Lectures"])


class LectureCreate(BaseModel):
    course_id: str
    lecturer_id: str
    title: str
    lecture_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/")
def create_lecture(payload: LectureCreate, db: Session = Depends(get_db)):
    lecturer = db.query(Lecturer).filter(Lecturer.id == payload.lecturer_id).first()
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

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

    return {
        "id": lecture.id,
        "course_id": lecture.course_id,
        "lecturer_id": lecture.lecturer_id,
        "title": lecture.title,
        "lecture_date": lecture.lecture_date,
        "notes": lecture.notes,
        "created_at": lecture.created_at,
    }


@router.get("/course/{course_id}")
def get_course_lectures(course_id: str, db: Session = Depends(get_db)):
    lectures = db.query(Lecture).filter(Lecture.course_id == course_id).all()

    result = []
    for lecture in lectures:
        lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()

        result.append({
            "id": lecture.id,
            "course_id": lecture.course_id,
            "lecturer_id": lecture.lecturer_id,
            "lecturer_name": lecturer.full_name if lecturer else None,
            "title": lecture.title,
            "lecture_date": lecture.lecture_date,
            "notes": lecture.notes,
            "created_at": lecture.created_at,
        })

    return result
EOF

echo "Updating documents route..."
cat > app/routes/documents.py <<'EOF'
import os
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
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

    chunking_agent = ChunkingAgent()
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
        cs_agent = CourseSummaryAgent()
        course_summary_text = cs_agent.summarize_course(
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
EOF

echo "Updating copilot route..."
cat > app/routes/copilot.py <<'EOF'
from typing import Optional
import json
import requests

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap

from app.agents.router_agent import RouterAgent
from app.services.vector_store import VectorStoreService
from app.utils.language_utils import detect_text_language

router = APIRouter(prefix="/copilot", tags=["Copilot"])


class CopilotRequest(BaseModel):
    course_id: str
    question: str
    language: Optional[str] = None


def latest_course_summary(db: Session, course_id: str):
    return (
        db.query(CourseSummary)
        .filter(CourseSummary.course_id == course_id)
        .order_by(CourseSummary.created_at.desc())
        .first()
    )


def latest_knowledge_map(db: Session, course_id: str):
    return (
        db.query(KnowledgeMap)
        .filter(KnowledgeMap.course_id == course_id)
        .order_by(KnowledgeMap.created_at.desc())
        .first()
    )


def build_prompt(intent: str, course_id: str, question: str, language: str, db: Session):
    if intent == "qa":
        vector_store = VectorStoreService()
        results = vector_store.search_chunks(
            course_id=course_id,
            query=question,
            top_k=10
        )

        chunks = []
        sources = []

        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results["metadatas"][0]

            for doc, meta in zip(docs, metas):
                chunks.append(doc)
                sources.append(meta)

        context = "\n\n".join(chunks[:5])

        if language == "he":
            prompt = f"""
ענה על השאלה על בסיס חומר הקורס בלבד.

אם התשובה לא מופיעה בחומר, אמור זאת בבירור.

חומר רלוונטי:
{context}

שאלה:
{question}

ענה בעברית, בצורה ברורה ומסודרת.
"""
        else:
            prompt = f"""
Answer the question based only on the course material below.

If the answer is not contained in the material, say so clearly.

Relevant course material:
{context}

Question:
{question}

Answer clearly and in English.
"""
        return prompt, sources

    if intent == "course_summary":
        cs = latest_course_summary(db, course_id)
        if not cs:
            raise HTTPException(status_code=404, detail="No course summary found")
        return cs.summary_text, []

    if intent == "knowledge_map":
        km = latest_knowledge_map(db, course_id)
        if not km:
            raise HTTPException(status_code=404, detail="No knowledge map found")
        return km.map_text, []

    if intent == "exam":
        cs = latest_course_summary(db, course_id)
        if not cs:
            raise HTTPException(status_code=404, detail="No course summary found")

        if language == "he":
            prompt = f"""
על בסיס סיכום הקורס הבא צור מבחן בפורמט JSON תקין בלבד.

מבנה ה-JSON חייב להיות בדיוק כך:
{{
  "multiple_choice": [
    {{
      "question": "שאלה",
      "options": ["א", "ב", "ג", "ד"],
      "answer": "א"
    }}
  ],
  "open_questions": [
    {{
      "question": "שאלה פתוחה",
      "answer_guidance": "קו מנחה לתשובה"
    }}
  ],
  "advanced_questions": [
    {{
      "question": "שאלת חשיבה",
      "answer_guidance": "קו מנחה לתשובה"
    }}
  ]
}}

דרישות:
- 5 שאלות אמריקאיות
- 3 שאלות פתוחות
- 2 שאלות מתקדמות
- החזר JSON בלבד

סיכום הקורס:
{cs.summary_text}
"""
        else:
            prompt = f"""
Based on the course summary below, generate an exam in valid JSON only.

The JSON must match exactly this structure:
{{
  "multiple_choice": [
    {{
      "question": "Question text",
      "options": ["A", "B", "C", "D"],
      "answer": "A"
    }}
  ],
  "open_questions": [
    {{
      "question": "Open question",
      "answer_guidance": "What a good answer should include"
    }}
  ],
  "advanced_questions": [
    {{
      "question": "Advanced thinking question",
      "answer_guidance": "What a good answer should include"
    }}
  ]
}}

Requirements:
- 5 multiple choice questions
- 3 open questions
- 2 advanced questions
- Return JSON only

Course summary:
{cs.summary_text}
"""
        return prompt, []

    return "Answer the user's question.", []


@router.post("/ask")
def ask_copilot(payload: CopilotRequest, db: Session = Depends(get_db)):
    question_language = detect_text_language(payload.question)
    router_agent = RouterAgent()
    intent = router_agent.detect_intent(payload.question)

    prompt, sources = build_prompt(
        intent=intent,
        course_id=payload.course_id,
        question=payload.question,
        language=question_language,
        db=db,
    )

    if intent in {"course_summary", "knowledge_map"}:
        return {
            "intent": intent,
            "question": payload.question,
            "detected_language": question_language,
            "answer": prompt,
            "sources": sources,
        }

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.1",
            "prompt": prompt,
            "stream": False
        },
        timeout=300
    )
    response.raise_for_status()
    answer = response.json().get("response", "").strip()

    result = {
        "intent": intent,
        "question": payload.question,
        "detected_language": question_language,
        "answer": answer,
        "sources": sources,
    }

    if intent == "exam":
        try:
            result["exam"] = json.loads(answer)
        except Exception:
            result["exam"] = {"raw": answer}

    return result


@router.post("/ask-stream")
def ask_copilot_stream(payload: CopilotRequest, db: Session = Depends(get_db)):
    question_language = detect_text_language(payload.question)
    router_agent = RouterAgent()
    intent = router_agent.detect_intent(payload.question)

    prompt, sources = build_prompt(
        intent=intent,
        course_id=payload.course_id,
        question=payload.question,
        language=question_language,
        db=db,
    )

    def event_stream():
        yield json.dumps({
            "type": "meta",
            "intent": intent,
            "sources": sources,
            "detected_language": question_language
        }) + "\n"

        if intent in {"course_summary", "knowledge_map"}:
            yield json.dumps({"type": "chunk", "content": prompt}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
            return

        with requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.1",
                "prompt": prompt,
                "stream": True
            },
            stream=True,
            timeout=300
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                obj = json.loads(line.decode("utf-8"))
                chunk = obj.get("response", "")
                done = obj.get("done", False)

                if chunk:
                    yield json.dumps({"type": "chunk", "content": chunk}) + "\n"

                if done:
                    yield json.dumps({"type": "done"}) + "\n"
                    break

    return StreamingResponse(event_stream(), media_type="text/plain")
EOF

echo "Adding lecture_id column to documents if missing..."
python <<'PYEOF'
import sqlite3

conn = sqlite3.connect("learning_copilot.db")
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(documents)")
columns = [row[1] for row in cursor.fetchall()]

if "lecture_id" not in columns:
    cursor.execute("ALTER TABLE documents ADD COLUMN lecture_id TEXT")
    print("Added documents.lecture_id")
else:
    print("documents.lecture_id already exists")

conn.commit()
conn.close()
PYEOF

echo "Updating main.py..."
cat > app/main.py <<'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine

from app.routes.courses import router as courses_router
from app.routes.lecturers import router as lecturers_router
from app.routes.lectures import router as lectures_router
from app.routes.documents import router as documents_router
from app.routes.summaries import router as summaries_router
from app.routes.qa import router as qa_router
from app.routes.course_summaries import router as course_summaries_router
from app.routes.knowledge_maps import router as knowledge_maps_router
from app.routes.copilot import router as copilot_router

from app.models.course import Course
from app.models.lecturer import Lecturer
from app.models.lecture import Lecture
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Learning Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(courses_router)
app.include_router(lecturers_router)
app.include_router(lectures_router)
app.include_router(documents_router)
app.include_router(summaries_router)
app.include_router(qa_router)
app.include_router(course_summaries_router)
app.include_router(knowledge_maps_router)
app.include_router(copilot_router)


@app.get("/")
def root():
    return {"message": "Learning Copilot API is running"}
EOF

echo "Backend domain upgrade completed."
