from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class ExamQuestionCreate(BaseModel):
    source_type: str = "public_bank"
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None
    topic: str
    difficulty: Literal["easy", "medium", "hard", "case"] = "medium"
    question_type: Literal["mcq", "open", "case"] = "mcq"
    question_text: str
    options: Optional[List[str]] = None
    correct_answer_text: str
    correct_answer_index: Optional[int] = None
    explanation: Optional[str] = None
    source_ref: Optional[str] = None
    language: str = "he"
    is_active: bool = True


class ExamQuestionResponse(BaseModel):
    id: str
    source_type: str
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None
    topic: str
    difficulty: str
    question_type: str
    question_text: str
    options: Optional[List[str]] = None
    correct_answer_text: str
    correct_answer_index: Optional[int] = None
    explanation: Optional[str] = None
    source_ref: Optional[str] = None
    language: str
    is_active: bool

    class Config:
        from_attributes = True


class GenerateSimulationRequest(BaseModel):
    mode: Literal["full", "topic", "course_material"] = "full"
    course_id: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[Literal["easy", "medium", "hard", "case", "mixed"]] = "mixed"
    question_count: int = Field(default=10, ge=1, le=100)
    language: str = "he"
    include_course_material: bool = True
    include_public_bank: bool = True


class SimulationQuestionResponse(BaseModel):
    simulation_question_id: str
    question_id: str
    topic: str
    difficulty: str
    question_type: str
    question_text: str
    options: Optional[List[str]] = None


class GenerateSimulationResponse(BaseModel):
    simulation_id: str
    question_count: int
    questions: List[SimulationQuestionResponse]


class SubmitAnswerRequest(BaseModel):
    simulation_question_id: str
    user_answer_index: Optional[int] = None
    user_answer_text: Optional[str] = None


class SubmitAnswerResponse(BaseModel):
    is_correct: bool
    correct_answer_index: Optional[int] = None
    correct_answer_text: str
    explanation: Optional[str] = None


class SimulationResultResponse(BaseModel):
    score: int
    max_score: int
    percentage: float
    weak_topics: List[str]


class TopicPerformanceItem(BaseModel):
    topic: str
    correct_count: int
    wrong_count: int
