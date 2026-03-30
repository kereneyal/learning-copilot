from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lecturer import Lecturer

router = APIRouter(prefix="/lecturers", tags=["Lecturers"])


class LecturerCreate(BaseModel):
    full_name: str
    bio: Optional[str] = None


@router.post("/")
def create_lecturer(payload: LecturerCreate, db: Session = Depends(get_db)):
    lecturer = Lecturer(
        full_name=payload.full_name,
        bio=payload.bio
    )
    db.add(lecturer)
    db.commit()
    db.refresh(lecturer)

    return {
        "id": lecturer.id,
        "full_name": lecturer.full_name,
        "bio": lecturer.bio,
        "created_at": lecturer.created_at,
    }


@router.get("/")
def list_lecturers(db: Session = Depends(get_db)):
    lecturers = db.query(Lecturer).all()

    return [
        {
            "id": lecturer.id,
            "full_name": lecturer.full_name,
            "bio": lecturer.bio,
            "created_at": lecturer.created_at,
        }
        for lecturer in lecturers
    ]
