from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class KnowledgeMap(Base):
    __tablename__ = "knowledge_maps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(String, nullable=False)
    map_text = Column(Text, nullable=False)
    language = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
