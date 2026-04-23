import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func

from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    lecture_id = Column(String, ForeignKey("lectures.id"), nullable=True)

    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)

    language = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    topic = Column(String, nullable=True)

    raw_text = Column(Text, nullable=True)
    processing_status = Column(String, nullable=True, default="ready")
    processing_progress = Column(Integer, nullable=True, default=0)
    error_type = Column(String, nullable=True)
    error_stage = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    summary_status = Column(String, nullable=True, default="not_started")

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
