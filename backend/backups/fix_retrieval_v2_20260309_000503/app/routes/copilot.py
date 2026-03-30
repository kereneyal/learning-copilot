from fastapi import APIRouter
from pydantic import BaseModel
from app.agents.qa_agent import answer_question


router = APIRouter()


class QuestionRequest(BaseModel):

    course_id: str
    question: str


@router.post("/copilot/ask")

def ask(req: QuestionRequest):

    result = answer_question(req.course_id, req.question)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "intent": "qa"
    }
