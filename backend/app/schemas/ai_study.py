from pydantic import BaseModel
from typing import List, Literal


class AIStudyRequest(BaseModel):
    text: str
    mode: Literal["summary", "flashcards", "quiz"] = "summary"


class FlashcardItem(BaseModel):
    question: str
    answer: str


class QuizItem(BaseModel):
    question: str
    answer: str


class AIStudyResponse(BaseModel):
    summary: str
    flashcards: List[FlashcardItem]
    quiz: List[QuizItem]
    provider: str
