from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    language = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    session_number = Column(String, nullable=True)
    topic = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
