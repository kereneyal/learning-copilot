from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lecturer import Lecturer
from app.models.lecture import Lecture

router = APIRouter(prefix="/lecturers", tags=["Lecturers"])


class LecturerCreate(BaseModel):
    full_name: str
    bio: Optional[str] = None


class LecturerUpdate(BaseModel):
    full_name: Optional[str] = None
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


@router.put("/{lecturer_id}")
def update_lecturer(lecturer_id: str, payload: LecturerUpdate, db: Session = Depends(get_db)):
    lecturer = db.query(Lecturer).filter(Lecturer.id == lecturer_id).first()
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    if payload.full_name is not None:
        lecturer.full_name = payload.full_name
    if payload.bio is not None:
        lecturer.bio = payload.bio

    db.commit()
    db.refresh(lecturer)

    return {
        "id": lecturer.id,
        "full_name": lecturer.full_name,
        "bio": lecturer.bio,
        "created_at": lecturer.created_at,
    }


@router.delete("/{lecturer_id}")
def delete_lecturer(lecturer_id: str, db: Session = Depends(get_db)):
    lecturer = db.query(Lecturer).filter(Lecturer.id == lecturer_id).first()
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    linked_lectures = db.query(Lecture).filter(Lecture.lecturer_id == lecturer_id).count()
    if linked_lectures > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete lecturer with linked lectures"
        )

    db.delete(lecturer)
    db.commit()

    return {
        "status": "deleted",
        "deleted_lecturer_id": lecturer_id
    }
