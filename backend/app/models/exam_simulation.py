import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.database import Base


class ExamSimulation(Base):
    __tablename__ = "exam_simulations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_session_id = Column(String, nullable=True)

    course_id = Column(String, nullable=True)
    mode = Column(String, nullable=False, default="full")  # full / topic / course_material
    topic = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)

    question_count = Column(Integer, nullable=False, default=10)
    status = Column(String, nullable=False, default="in_progress")  # in_progress / completed

    score = Column(Integer, nullable=True)
    max_score = Column(Integer, nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
