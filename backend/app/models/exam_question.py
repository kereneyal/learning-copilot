import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer
from sqlalchemy.sql import func
from app.db.database import Base


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(String, nullable=False, default="public_bank")
    course_id = Column(String, nullable=True)
    lecture_id = Column(String, nullable=True)

    topic = Column(String, nullable=False)
    difficulty = Column(String, nullable=False, default="medium")   # easy / medium / hard / case
    question_type = Column(String, nullable=False, default="mcq")   # mcq / open / case

    question_text = Column(Text, nullable=False)
    options_json = Column(Text, nullable=True)  # JSON string
    correct_answer_text = Column(Text, nullable=False)
    correct_answer_index = Column(Integer, nullable=True)
    explanation = Column(Text, nullable=True)

    source_ref = Column(String, nullable=True)
    language = Column(String, nullable=False, default="he")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
