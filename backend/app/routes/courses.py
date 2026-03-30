from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.course import Course
from app.models.lecture import Lecture
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/courses", tags=["Courses"])


class CourseCreate(BaseModel):
    name: str
    institution: Optional[str] = None
    default_language: Optional[str] = "en"
    semester: Optional[str] = None
    lecturer_name: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    default_language: Optional[str] = None
    semester: Optional[str] = None
    lecturer_name: Optional[str] = None


@router.post("/")
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Course name is required")

    course = Course(
        name=payload.name.strip(),
        institution=payload.institution,
        default_language=payload.default_language,
        semester=payload.semester,
        lecturer_name=payload.lecturer_name,
    )

    db.add(course)
    db.commit()
    db.refresh(course)

    return {
        "id": course.id,
        "name": course.name,
        "institution": course.institution,
        "default_language": course.default_language,
        "semester": course.semester,
        "lecturer_name": course.lecturer_name,
        "created_at": course.created_at,
    }


@router.get("/")
def list_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).all()

    return [
        {
            "id": course.id,
            "name": course.name,
            "institution": course.institution,
            "default_language": getattr(course, "default_language", None),
            "semester": course.semester,
            "lecturer_name": getattr(course, "lecturer_name", None),
            "created_at": course.created_at,
        }
        for course in courses
    ]


@router.put("/{course_id}")
def update_course(course_id: str, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="Course name cannot be empty")
        course.name = payload.name.strip()
    if payload.institution is not None:
        course.institution = payload.institution
    if payload.default_language is not None:
        course.default_language = payload.default_language
    if payload.semester is not None:
        course.semester = payload.semester
    if payload.lecturer_name is not None:
        course.lecturer_name = payload.lecturer_name

    db.commit()
    db.refresh(course)

    return {
        "id": course.id,
        "name": course.name,
        "institution": course.institution,
        "default_language": getattr(course, "default_language", None),
        "semester": course.semester,
        "lecturer_name": getattr(course, "lecturer_name", None),
        "created_at": course.created_at,
    }


@router.delete("/{course_id}")
def delete_course(course_id: str, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    vector_store = VectorStoreService()

    documents = db.query(Document).filter(Document.course_id == course_id).all()
    document_ids = [doc.id for doc in documents]

    if document_ids:
        db.query(Summary).filter(Summary.document_id.in_(document_ids)).delete(synchronize_session=False)

    db.query(Document).filter(Document.course_id == course_id).delete(synchronize_session=False)
    db.query(Lecture).filter(Lecture.course_id == course_id).delete(synchronize_session=False)
    db.query(CourseSummary).filter(CourseSummary.course_id == course_id).delete(synchronize_session=False)
    db.query(KnowledgeMap).filter(KnowledgeMap.course_id == course_id).delete(synchronize_session=False)

    vector_store.delete_by_course_id(course_id)

    db.delete(course)
    db.commit()

    return {
        "status": "deleted",
        "deleted_course_id": course_id
    }
