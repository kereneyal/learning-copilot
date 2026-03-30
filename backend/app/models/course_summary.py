from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class CourseSummary(Base):
    __tablename__ = "course_summaries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    summary_text = Column(Text, nullable=False)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

