#!/bin/bash

set -e

echo "Writing app/models/knowledge_map.py..."
cat > app/models/knowledge_map.py <<'EOF'
from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class KnowledgeMap(Base):
    __tablename__ = "knowledge_maps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    map_text = Column(Text, nullable=False)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
EOF

echo "Writing app/agents/exam_agent.py..."
cat > app/agents/exam_agent.py <<'EOF'
import requests
import json


class ExamAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def generate_exam(self, course_summary: str, language: str = "en") -> str:
        prompt = self._build_prompt(course_summary, language)

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            },
            timeout=180
        )

        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def _build_prompt(self, course_summary: str, language: str) -> str:
        if language == "he":
            return f"""
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
- החזר JSON בלבד, בלי הסברים, בלי markdown

סיכום הקורס:
{course_summary}
"""
        else:
            return f"""
Based on the following course summary, generate an exam in valid JSON only.

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
- Return JSON only, no markdown, no explanations

Course summary:
{course_summary}
"""
EOF

echo "Writing app/routes/knowledge_maps.py..."
cat > app/routes/knowledge_maps.py <<'EOF'
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.knowledge_map import KnowledgeMap

router = APIRouter(prefix="/knowledge-maps", tags=["Knowledge Maps"])


@router.get("/course/{course_id}")
def get_latest_knowledge_map(course_id: str, db: Session = Depends(get_db)):
    km = (
        db.query(KnowledgeMap)
        .filter(KnowledgeMap.course_id == course_id)
        .order_by(KnowledgeMap.created_at.desc())
        .first()
    )

    if not km:
        raise HTTPException(status_code=404, detail="No knowledge map found")

    return {
        "id": km.id,
        "course_id": km.course_id,
        "language": km.language,
        "map_text": km.map_text,
        "created_at": km.created_at,
    }
EOF

echo "Writing app/routes/documents.py with auto-processing..."
cat > app/routes/documents.py <<'EOF'
import os
import shutil
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
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


@router.post("/upload")
def upload_document(
    course_id: str = Form(...),
    session_number: Optional[str] = Form(None),
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
        file_name=file.filename,
        file_path=saved_file_path,
        file_type=file_extension,
        language=detected_language,
        source_type=source_type,
        session_number=session_number,
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

    # auto document summary
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
    db.refresh(new_summary)

    # auto course summary refresh
    all_summaries = (
        db.query(Summary)
        .join(Document, Summary.document_id == Document.id)
        .filter(Document.course_id == course_id)
        .all()
    )

    summaries_texts = [s.summary_text for s in all_summaries if s.summary_text]

    course_summary_text = ""
    latest_knowledge_map_text = ""

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
        db.refresh(cs)

        # auto knowledge map refresh
        km_agent = KnowledgeMapAgent()
        latest_knowledge_map_text = km_agent.generate_map(
            course_summary=course_summary_text,
            document_summaries=summaries_texts,
            language=new_document.language or "en"
        )

        km = KnowledgeMap(
            course_id=course_id,
            map_text=latest_knowledge_map_text,
            language=new_document.language
        )
        db.add(km)
        db.commit()
        db.refresh(km)

    return {
        "id": new_document.id,
        "course_id": new_document.course_id,
        "file_name": new_document.file_name,
        "file_type": new_document.file_type,
        "language": new_document.language,
        "session_number": new_document.session_number,
        "topic": new_document.topic,
        "source_type": new_document.source_type,
        "chunks_count": len(chunks),
        "raw_text_preview": extracted_text[:500],
        "document_summary_created": True,
        "course_summary_refreshed": bool(course_summary_text),
        "knowledge_map_refreshed": bool(latest_knowledge_map_text),
    }


@router.get("/course/{course_id}")
def get_documents_by_course(course_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.course_id == course_id).all()

    return [
        {
            "id": doc.id,
            "course_id": doc.course_id,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "language": doc.language,
            "session_number": doc.session_number,
            "topic": doc.topic,
            "source_type": doc.source_type,
            "uploaded_at": doc.uploaded_at,
        }
        for doc in documents
    ]
EOF

echo "Writing app/routes/copilot.py with structured exam JSON..."
cat > app/routes/copilot.py <<'EOF'
from typing import Optional
import json
import requests

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap

from app.agents.router_agent import RouterAgent
from app.agents.qa_agent import QAAgent
from app.agents.course_summary_agent import CourseSummaryAgent
from app.agents.knowledge_map_agent import KnowledgeMapAgent
from app.agents.exam_agent import ExamAgent

from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/copilot", tags=["Copilot"])


class CopilotRequest(BaseModel):
    course_id: str
    question: str
    language: Optional[str] = "en"


@router.post("/ask")
def ask_copilot(payload: CopilotRequest, db: Session = Depends(get_db)):
    router_agent = RouterAgent()
    intent = router_agent.detect_intent(payload.question)

    if intent == "qa":
        vector_store = VectorStoreService()

        results = vector_store.search_chunks(
            course_id=payload.course_id,
            query=payload.question,
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

        qa_agent = QAAgent()

        answer = qa_agent.answer_question(
            question=payload.question,
            context_chunks=chunks,
            language=payload.language or "en"
        )

        return {
            "intent": intent,
            "question": payload.question,
            "answer": answer,
            "sources": sources
        }

    elif intent == "course_summary":
        course_summary = (
            db.query(CourseSummary)
            .filter(CourseSummary.course_id == payload.course_id)
            .order_by(CourseSummary.created_at.desc())
            .first()
        )

        if not course_summary:
            raise HTTPException(status_code=404, detail="No course summary found")

        return {
            "intent": intent,
            "question": payload.question,
            "answer": course_summary.summary_text,
            "sources": []
        }

    elif intent == "knowledge_map":
        km = (
            db.query(KnowledgeMap)
            .filter(KnowledgeMap.course_id == payload.course_id)
            .order_by(KnowledgeMap.created_at.desc())
            .first()
        )

        if not km:
            raise HTTPException(status_code=404, detail="No knowledge map found")

        return {
            "intent": intent,
            "question": payload.question,
            "answer": km.map_text,
            "sources": []
        }

    elif intent == "exam":
        course_summary = (
            db.query(CourseSummary)
            .filter(CourseSummary.course_id == payload.course_id)
            .order_by(CourseSummary.created_at.desc())
            .first()
        )

        if not course_summary:
            raise HTTPException(status_code=404, detail="No course summary found")

        agent = ExamAgent()
        exam_text = agent.generate_exam(
            course_summary.summary_text,
            payload.language or "en"
        )

        parsed = None
        try:
            parsed = json.loads(exam_text)
        except Exception:
            parsed = {"raw": exam_text}

        return {
            "intent": intent,
            "question": payload.question,
            "answer": exam_text,
            "exam": parsed,
            "sources": []
        }

    return {
        "intent": "qa",
        "question": payload.question,
        "answer": "Fallback response",
        "sources": []
    }


def build_prompt_for_streaming(intent: str, payload: CopilotRequest, db: Session):
    if intent == "qa":
        vector_store = VectorStoreService()
        results = vector_store.search_chunks(
            course_id=payload.course_id,
            query=payload.question,
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

        if (payload.language or "en") == "he":
            prompt = f"""
ענה על השאלה על בסיס חומר הקורס בלבד.

אם התשובה לא מופיעה בחומר, אמור זאת בבירור.

חומר רלוונטי:
{context}

שאלה:
{payload.question}

ענה בעברית, בצורה ברורה ומסודרת.
"""
        else:
            prompt = f"""
Answer the question based only on the course material below.

If the answer is not contained in the material, say so clearly.

Relevant course material:
{context}

Question:
{payload.question}

Answer clearly and in English.
"""
        return prompt, sources, intent

    elif intent == "course_summary":
        course_summary = (
            db.query(CourseSummary)
            .filter(CourseSummary.course_id == payload.course_id)
            .order_by(CourseSummary.created_at.desc())
            .first()
        )

        if not course_summary:
            raise HTTPException(status_code=404, detail="No course summary found")

        return course_summary.summary_text, [], intent

    elif intent == "knowledge_map":
        km = (
            db.query(KnowledgeMap)
            .filter(KnowledgeMap.course_id == payload.course_id)
            .order_by(KnowledgeMap.created_at.desc())
            .first()
        )

        if not km:
            raise HTTPException(status_code=404, detail="No knowledge map found")

        return km.map_text, [], intent

    elif intent == "exam":
        course_summary = (
            db.query(CourseSummary)
            .filter(CourseSummary.course_id == payload.course_id)
            .order_by(CourseSummary.created_at.desc())
            .first()
        )

        if not course_summary:
            raise HTTPException(status_code=404, detail="No course summary found")

        if (payload.language or "en") == "he":
            prompt = f"""
על בסיס סיכום הקורס הבא צור מבחן.

המבחן צריך לכלול:
1. 5 שאלות רב ברירה
2. 3 שאלות פתוחות
3. 2 שאלות חשיבה מתקדמות

ספק גם תשובות.

סיכום הקורס:
{course_summary.summary_text}
"""
        else:
            prompt = f"""
Based on the course summary below, generate an exam.

The exam must include:
1. 5 multiple choice questions
2. 3 open questions
3. 2 advanced thinking questions

Also include answers.

Course summary:
{course_summary.summary_text}
"""
        return prompt, [], intent

    return "Answer the user's question.", [], "qa"


@router.post("/ask-stream")
def ask_copilot_stream(payload: CopilotRequest, db: Session = Depends(get_db)):
    router_agent = RouterAgent()
    intent = router_agent.detect_intent(payload.question)

    prompt, sources, resolved_intent = build_prompt_for_streaming(intent, payload, db)

    def event_stream():
        header = {"type": "meta", "intent": resolved_intent, "sources": sources}
        yield json.dumps(header) + "\n"

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

echo "Writing app/main.py..."
cat > app/main.py <<'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine

from app.routes.courses import router as courses_router
from app.routes.documents import router as documents_router
from app.routes.summaries import router as summaries_router
from app.routes.qa import router as qa_router
from app.routes.course_summaries import router as course_summaries_router
from app.routes.knowledge_maps import router as knowledge_maps_router
from app.routes.copilot import router as copilot_router

from app.models.course import Course
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

echo "Backend upgraded successfully."
