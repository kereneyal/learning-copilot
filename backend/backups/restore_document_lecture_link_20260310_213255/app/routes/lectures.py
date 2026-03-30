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
    lecturer_id: Optional[str] = None
    title: str
    lecture_date: Optional[str] = None
    notes: Optional[str] = None


class LectureUpdate(BaseModel):
    lecturer_id: Optional[str] = None
    title: Optional[str] = None
    lecture_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/")
def create_lecture(payload: LectureCreate, db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Lecture title is required")

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

    lecturer_name = None
    if lecture.lecturer_id:
        lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()
        if lecturer:
            lecturer_name = lecturer.full_name

    return {
        "id": lecture.id,
        "course_id": lecture.course_id,
        "lecturer_id": lecture.lecturer_id,
        "lecturer_name": lecturer_name,
        "title": lecture.title,
        "lecture_date": lecture.lecture_date,
        "notes": lecture.notes,
    }


@router.get("/course/{course_id}")
def get_lectures_by_course(course_id: str, db: Session = Depends(get_db)):
    lectures = db.query(Lecture).filter(Lecture.course_id == course_id).all()

    result = []
    for lecture in lectures:
        lecturer_name = None

        if lecture.lecturer_id:
            lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()
            if lecturer:
                lecturer_name = lecturer.full_name

        result.append({
            "id": lecture.id,
            "course_id": lecture.course_id,
            "lecturer_id": lecture.lecturer_id,
            "lecturer_name": lecturer_name,
            "title": lecture.title,
            "lecture_date": lecture.lecture_date,
            "notes": lecture.notes,
        })

    return result


@router.put("/{lecture_id}")
def update_lecture(lecture_id: str, payload: LectureUpdate, db: Session = Depends(get_db)):
    lecture = db.query(Lecture).filter(Lecture.id == lecture_id).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    if payload.lecturer_id is not None:
        lecture.lecturer_id = payload.lecturer_id

    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Lecture title cannot be empty")
        lecture.title = payload.title

    if payload.lecture_date is not None:
        lecture.lecture_date = payload.lecture_date

    if payload.notes is not None:
        lecture.notes = payload.notes

    db.commit()
    db.refresh(lecture)

    lecturer_name = None
    if lecture.lecturer_id:
        lecturer = db.query(Lecturer).filter(Lecturer.id == lecture.lecturer_id).first()
        if lecturer:
            lecturer_name = lecturer.full_name

    return {
        "id": lecture.id,
        "course_id": lecture.course_id,
        "lecturer_id": lecture.lecturer_id,
        "lecturer_name": lecturer_name,
        "title": lecture.title,
        "lecture_date": lecture.lecture_date,
        "notes": lecture.notes,
    }


@router.delete("/{lecture_id}")
def delete_lecture(lecture_id: str, db: Session = Depends(get_db)):
    lecture = db.query(Lecture).filter(Lecture.id == lecture_id).first()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    db.delete(lecture)
    db.commit()

    return {
        "status": "deleted",
        "deleted_lecture_id": lecture_id,
    }
