from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from sqlalchemy.orm import Session
from app.db.database import get_db
from app.agents.qa_agent import QAAgent
from app.services.course_resolver import resolve_course_from_question
from app.services.global_search_service import search_everywhere

router = APIRouter()
agent = QAAgent()


def _normalize_search_query(question: str) -> str:
    q = (question or "").strip()

    prefixes = [
        "איפה דיברו על",
        "איפה מדברים על",
        "מצא לי",
        "חפש לי",
        "מה זה",
        "מהו",
        "מהי",
        "ספר לי על",
        "הסבר לי על",
        "מה נאמר על",
    ]

    for prefix in prefixes:
        if q.startswith(prefix):
            q = q[len(prefix):].strip()

    return q.strip(" ?!.,")



def _merge_sources(primary: list, secondary: list, limit: int = 8) -> list:
    merged = []
    seen = set()

    for item in (primary or []) + (secondary or []):
        key = (
            item.get("type"),
            item.get("course_id"),
            item.get("lecture_id"),
            item.get("document_id"),
            item.get("title") or item.get("document_name"),
            item.get("snippet"),
            item.get("chunk_index"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= limit:
            break

    return merged


def _is_search_intent(question: str) -> bool:
    q = (question or "").strip()
    patterns = [
        "איפה דיברו על",
        "איפה מדברים על",
        "מצא לי",
        "חפש לי",
        "באיזה הרצאה",
        "באילו הרצאות",
        "באיזה מסמך",
        "באילו מסמכים",
        "איפה מופיע",
        "איפה מופיעה",
        "where did they talk about",
        "find me",
        "where is",
        "which lecture",
        "which document",
    ]
    q_lower = q.lower()
    return any(p in q_lower for p in patterns)


def _build_search_answer(question: str, search_results: list) -> str:
    if not search_results:
        return "לא מצאתי תוצאות רלוונטיות לשאלה."

    lectures = []
    documents = []
    summaries = []
    chunks = []

    seen_lectures = set()
    seen_documents = set()

    for item in search_results:
        item_type = item.get("type")
        if item_type == "lecture":
            key = item.get("lecture_id") or item.get("title")
            if key not in seen_lectures:
                seen_lectures.add(key)
                lectures.append(item)
        elif item_type in {"document", "summary"}:
            key = item.get("document_id") or item.get("title")
            if key not in seen_documents:
                seen_documents.add(key)
                if item_type == "document":
                    documents.append(item)
                else:
                    summaries.append(item)
        elif item_type == "chunk":
            chunks.append(item)

    lines = []

    normalized_question = (question or "").strip()

    if lectures:
        lines.append("מצאתי אזכורים רלוונטיים בעיקר בהרצאות הבאות:")
        for lecture in lectures[:6]:
            title = lecture.get("lecture_title") or lecture.get("title") or "ללא כותרת"
            lines.append(f"- {title}")

    if documents and not lectures:
        lines.append("מצאתי אזכורים רלוונטיים בעיקר במסמכים הבאים:")
        for doc in documents[:5]:
            title = doc.get("document_name") or doc.get("title") or "ללא כותרת"
            lines.append(f"- {title}")

    if summaries:
        lines.append("")
        lines.append("סיכומים רלוונטיים שנמצאו:")
        for s in summaries[:3]:
            title = s.get("document_name") or s.get("title") or "ללא כותרת"
            lines.append(f"- {title}")

    if chunks:
        best_chunk = chunks[0]
        snippet = (best_chunk.get("snippet") or "").strip()
        if snippet:
            lines.append("")
            lines.append("קטע תוכן רלוונטי:")
            lines.append(snippet)

    if not lines:
        lines.append("מצאתי תוצאות חלקיות, אבל לא מספיק מידע כדי לענות בצורה ממוקדת.")

    return "\n".join(lines)




class QuestionRequest(BaseModel):
    question: str
    mode: Optional[str] = "auto"
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None


@router.post("/copilot/ask")
def ask(req: QuestionRequest, db: Session = Depends(get_db)):
    resolved_mode = req.mode or "auto"
    resolved_course_id = req.course_id
    resolution_confidence = 0.0

    if resolved_mode == "auto":
        detected_course_id, confidence = resolve_course_from_question(db, req.question)
        if detected_course_id:
            resolved_mode = "course"
            resolved_course_id = detected_course_id
            resolution_confidence = confidence
        else:
            resolved_mode = "global"

    elif resolved_mode == "lecture":
        if not req.lecture_id:
            resolved_mode = "global"

    elif resolved_mode == "course":
        if not req.course_id:
            resolved_mode = "global"

    search_query = _normalize_search_query(req.question)

    search_results = search_everywhere(
        db=db,
        q=search_query or req.question,
        course_id=resolved_course_id if resolved_mode in {"course", "lecture"} else None,
        limit=6,
    )

    # אם זו שאלת חיפוש ויש תוצאות – עונים ישירות מה-search
    if _is_search_intent(req.question) and search_results:
        merged_sources = _merge_sources([], search_results, limit=8)

        return {
            "answer": _build_search_answer(req.question, search_results),
            "sources": merged_sources,
            "search_results": search_results,
            "mode": resolved_mode,
            "resolved_course_id": resolved_course_id,
            "resolution_confidence": resolution_confidence
        }

    # אחרת משתמשים ב-QAAgent
    result = agent.answer(
        question=req.question,
        db=db,
        course_id=resolved_course_id if resolved_mode in {"course", "lecture"} else None,
        lecture_id=req.lecture_id if resolved_mode == "lecture" else None
    )

    merged_sources = _merge_sources(
        result.get("sources", []),
        search_results,
        limit=8,
    )

    answer_text = result["answer"]
    if _is_search_intent(req.question) and search_results:
        answer_text = _build_search_answer(req.question, search_results)

    return {
        "answer": answer_text,
        "sources": merged_sources,
        "search_results": search_results,
        "mode": resolved_mode,
        "resolved_course_id": resolved_course_id,
        "resolution_confidence": resolution_confidence
    }
