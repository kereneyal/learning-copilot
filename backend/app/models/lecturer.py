from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from app.db.database import Base
import uuid


class Lecturer(Base):
    __tablename__ = "lecturers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String, nullable=False)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
