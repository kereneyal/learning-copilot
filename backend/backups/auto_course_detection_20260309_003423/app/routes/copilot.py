from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.agents.qa_agent import QAAgent

router = APIRouter()

agent = QAAgent()


class QuestionRequest(BaseModel):

    question: str
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None


@router.post("/copilot/ask")

def ask(req: QuestionRequest):

    result = agent.answer(
        question=req.question,
        course_id=req.course_id,
        lecture_id=req.lecture_id
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"]
    }
