from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.course import Course

router = APIRouter(prefix="/courses", tags=["Courses"])


class CourseCreate(BaseModel):
    name: str
    institution: Optional[str] = None
    default_language: str = "he"
    semester: Optional[str] = None
    lecturer_name: Optional[str] = None


@router.post("/")
def create_course(course: CourseCreate, db: Session = Depends(get_db)):
    new_course = Course(
        name=course.name,
        institution=course.institution,
        default_language=course.default_language,
        semester=course.semester,
        lecturer_name=course.lecturer_name,
    )

    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    return {
        "id": new_course.id,
        "name": new_course.name,
        "institution": new_course.institution,
        "default_language": new_course.default_language,
        "semester": new_course.semester,
        "lecturer_name": new_course.lecturer_name,
        "created_at": new_course.created_at,
    }


@router.get("/")
def list_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).all()

    return [
        {
            "id": course.id,
            "name": course.name,
            "institution": course.institution,
            "default_language": course.default_language,
            "semester": course.semester,
            "lecturer_name": course.lecturer_name,
            "created_at": course.created_at,
        }
        for course in courses
    ]
