from sqlalchemy import Column, String, DateTime
from datetime import datetime
from app.db.database import Base
import uuid


class Course(Base):
    __tablename__ = "courses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    institution = Column(String, nullable=True)
    default_language = Column(String, nullable=False, default="he")
    semester = Column(String, nullable=True)
    lecturer_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
