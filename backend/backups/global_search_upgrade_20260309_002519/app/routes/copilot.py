from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.qa_agent import answer_question
from app.utils.language_utils import detect_text_language

router = APIRouter()


class QuestionRequest(BaseModel):
    course_id: str
    question: str


@router.post("/copilot/ask")
def ask(req: QuestionRequest):
    detected_language = detect_text_language(req.question)

    result = answer_question(
        course_id=req.course_id,
        question=req.question,
        language=detected_language
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "intent": "qa",
        "detected_language": detected_language
    }
