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
