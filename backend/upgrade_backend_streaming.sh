#!/bin/bash

set -e

echo "Writing streaming copilot route..."

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
        summaries = (
            db.query(Summary)
            .join(Document, Summary.document_id == Document.id)
            .filter(Document.course_id == payload.course_id)
            .all()
        )

        if not summaries:
            raise HTTPException(status_code=404, detail="No document summaries found")

        summaries_texts = [summary.summary_text for summary in summaries]

        agent = CourseSummaryAgent()

        course_summary_text = agent.summarize_course(
            summaries_texts,
            payload.language or "en"
        )

        return {
            "intent": intent,
            "question": payload.question,
            "answer": course_summary_text,
            "sources": []
        }

    elif intent == "knowledge_map":
        course_summary = (
            db.query(CourseSummary)
            .filter(CourseSummary.course_id == payload.course_id)
            .order_by(CourseSummary.created_at.desc())
            .first()
        )

        if not course_summary:
            raise HTTPException(status_code=404, detail="No course summary found")

        summaries = (
            db.query(Summary)
            .join(Document, Summary.document_id == Document.id)
            .filter(Document.course_id == payload.course_id)
            .all()
        )

        summaries_texts = [summary.summary_text for summary in summaries]

        agent = KnowledgeMapAgent()

        knowledge_map = agent.generate_map(
            course_summary=course_summary.summary_text,
            document_summaries=summaries_texts,
            language=payload.language or "en"
        )

        return {
            "intent": intent,
            "question": payload.question,
            "answer": knowledge_map,
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

        exam = agent.generate_exam(
            course_summary.summary_text,
            payload.language or "en"
        )

        return {
            "intent": intent,
            "question": payload.question,
            "answer": exam,
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
        summaries = (
            db.query(Summary)
            .join(Document, Summary.document_id == Document.id)
            .filter(Document.course_id == payload.course_id)
            .all()
        )

        if not summaries:
            raise HTTPException(status_code=404, detail="No document summaries found")

        summaries_texts = [summary.summary_text for summary in summaries]
        combined_summaries = "\n\n".join(summaries_texts[:20])

        if (payload.language or "en") == "he":
            prompt = f"""
אתה מסכם קורס שלם על בסיס סיכומים של מסמכים שונים.

צור סיכום כללי של הקורס בפורמט הבא:

1. נושא מרכזי של הקורס
2. נושאים עיקריים
3. רעיונות חשובים
4. סיכום קצר של הקורס

סיכומי המסמכים:
{combined_summaries[:15000]}
"""
        else:
            prompt = f"""
You are summarizing an entire course based on multiple document summaries.

Create a structured course summary in the following format:

1. Main course topic
2. Main topics covered
3. Important ideas
4. Short course summary

Document summaries:
{combined_summaries[:15000]}
"""
        return prompt, [], intent

    elif intent == "knowledge_map":
        course_summary = (
            db.query(CourseSummary)
            .filter(CourseSummary.course_id == payload.course_id)
            .order_by(CourseSummary.created_at.desc())
            .first()
        )

        if not course_summary:
            raise HTTPException(status_code=404, detail="No course summary found")

        summaries = (
            db.query(Summary)
            .join(Document, Summary.document_id == Document.id)
            .filter(Document.course_id == payload.course_id)
            .all()
        )

        summaries_texts = [summary.summary_text for summary in summaries]
        combined_summaries = "\n\n".join(summaries_texts[:20])

        if (payload.language or "en") == "he":
            prompt = f"""
אתה בונה מפת ידע לקורס.

על בסיס סיכום הקורס וסיכומי המסמכים, הפק את המידע הבא:

1. נושאים מרכזיים
2. מושגים חשובים
3. קשרים בין נושאים
4. שאלות אפשריות למבחן

החזר תשובה ברורה ומובנית בעברית.

סיכום הקורס:
{course_summary.summary_text}

סיכומי מסמכים:
{combined_summaries[:12000]}
"""
        else:
            prompt = f"""
You are building a knowledge map for a course.

Based on the course summary and document summaries, generate:

1. Main topics
2. Important concepts
3. Relationships between topics
4. Possible exam questions

Return a clear and structured answer in English.

Course summary:
{course_summary.summary_text}

Document summaries:
{combined_summaries[:12000]}
"""
        return prompt, [], intent

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

echo "Streaming backend route added."
