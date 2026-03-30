from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String, nullable=False)
    summary_text = Column(Text, nullable=False)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
