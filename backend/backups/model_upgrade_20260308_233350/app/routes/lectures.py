from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.lecture import Lecture
from app.models.lecturer import Lecturer

router = APIRouter(prefix="/lectures", tags=["Lectures"])


class LectureCreate(BaseModel):
    course_id: str
    lecturer_id: str
    title: str
    lecture_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/")
def create_lecture(payload: LectureCreate, db: Session = Depends(get_db)):
    lecturer = db.query(Lecturer).filter(Lecturer.id == payload.lecturer_id).first()
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    lecture = Lecture(
        course_id=payload.course_id,
        lecturer_id=payload.lecturer_id,
        title=payload.title,
        lecture_date=payload.lecture_date,
        notes=payload.notes,
    )

    db.add(lecture)
    db.commit()
    db.refresh(lecture)

    return {
        "id": lecture.id,
        "course_id": lecture.course_id,
        "lecturer_id": lecture.lecturer_id,
        "title": lecture.title,
        "lecture_date": lecture.lecture_date,
        "notes": lecture.notes,
        "created_at": lecture.created_at,
    }


@router.get("/course/{course_id}")
def get_course_lectures(course_id: str, db: Session = Depends(get_db)):
    lectures = db.query(Lecture).filter(Lecture.course_id == course_id).all()

    result = []
    for lecture in lectures:
        lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()

        result.append({
            "id": lecture.id,
            "course_id": lecture.course_id,
            "lecturer_id": lecture.lecturer_id,
            "lecturer_name": lecturer.full_name if lecturer else None,
            "title": lecture.title,
            "lecture_date": lecture.lecture_date,
            "notes": lecture.notes,
            "created_at": lecture.created_at,
        })

    return result
