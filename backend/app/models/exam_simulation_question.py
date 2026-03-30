import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.database import Base


class ExamSimulationQuestion(Base):
    __tablename__ = "exam_simulation_questions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_id = Column(String, nullable=False, index=True)
    question_id = Column(String, nullable=False, index=True)

    display_order = Column(Integer, nullable=False)

    user_answer_text = Column(Text, nullable=True)
    user_answer_index = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    feedback = Column(Text, nullable=True)

    answered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
