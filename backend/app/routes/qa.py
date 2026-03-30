from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.agents.qa_agent import QAAgent

router = APIRouter(prefix="/qa", tags=["QA"])


class QuestionRequest(BaseModel):
    course_id: str
    question: str
    language: Optional[str] = "he"


@router.post("/ask")
def ask_question(payload: QuestionRequest, db: Session = Depends(get_db)):
    qa_agent = QAAgent()

    result = qa_agent.answer(
        question=payload.question,
        db=db,
        course_id=payload.course_id,
        lecture_id=None,
    )

    if isinstance(result, dict):
        return {
            "question": payload.question,
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
        }

    return {
        "question": payload.question,
        "answer": result,
        "sources": [],
    }
