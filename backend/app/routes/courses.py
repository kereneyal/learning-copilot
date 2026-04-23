import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.response import paginated, success
from app.db.database import get_db
from app.models.course import Course
from app.models.course_summary import CourseSummary
from app.models.document import Document
from app.models.knowledge_map import KnowledgeMap
from app.models.lecture import Lecture
from app.models.summary import Summary
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/courses", tags=["Courses"])
logger = logging.getLogger(__name__)

_VALID_LANGUAGES = {"he", "en"}


# ── Request schemas ────────────────────────────────────────────────────────────

class CourseCreate(BaseModel):
    name: str
    institution: Optional[str] = None
    default_language: Optional[str] = "en"
    semester: Optional[str] = None
    lecturer_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Course name cannot be empty")
        return v.strip()

    @field_validator("default_language")
    @classmethod
    def language_valid(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _VALID_LANGUAGES:
            raise ValueError(f"default_language must be one of {sorted(_VALID_LANGUAGES)}")
        return v


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    default_language: Optional[str] = None
    semester: Optional[str] = None
    lecturer_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Course name cannot be empty")
        return v.strip() if v else v

    @field_validator("default_language")
    @classmethod
    def language_valid(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in _VALID_LANGUAGES:
            raise ValueError(f"default_language must be one of {sorted(_VALID_LANGUAGES)}")
        return v


# ── Helpers ────────────────────────────────────────────────────────────────────

def _course_dict(course: Course) -> dict:
    return {
        "id": course.id,
        "name": course.name,
        "institution": course.institution,
        "default_language": getattr(course, "default_language", None),
        "semester": course.semester,
        "lecturer_name": getattr(course, "lecturer_name", None),
        "created_at": course.created_at,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/", summary="Create a course", status_code=201)
def create_course(payload: CourseCreate, db: Session = Depends(get_db)):
    course = Course(
        name=payload.name,
        institution=payload.institution,
        default_language=payload.default_language,
        semester=payload.semester,
        lecturer_name=payload.lecturer_name,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    logger.info("course.created course_id=%s name=%r", course.id, course.name)
    return success(_course_dict(course), message="Course created")


@router.get("/", summary="List courses (paginated)")
def list_courses(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(50, ge=1, le=200, description="Results per page"),
    db: Session = Depends(get_db),
):
    total = db.query(Course).count()
    courses = (
        db.query(Course)
        .order_by(Course.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated(
        items=[_course_dict(c) for c in courses],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{course_id}", summary="Get a single course")
def get_course(course_id: str, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return success(_course_dict(course))


@router.put("/{course_id}", summary="Update a course")
def update_course(course_id: str, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if payload.name is not None:
        course.name = payload.name
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
    logger.info("course.updated course_id=%s", course_id)
    return success(_course_dict(course), message="Course updated")


@router.delete("/{course_id}", summary="Delete a course and all its data")
def delete_course(course_id: str, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    document_ids = [
        d.id for d in db.query(Document).filter(Document.course_id == course_id).all()
    ]
    if document_ids:
        db.query(Summary).filter(
            Summary.document_id.in_(document_ids)
        ).delete(synchronize_session=False)

    db.query(Document).filter(Document.course_id == course_id).delete(
        synchronize_session=False
    )
    db.query(Lecture).filter(Lecture.course_id == course_id).delete(
        synchronize_session=False
    )
    db.query(CourseSummary).filter(CourseSummary.course_id == course_id).delete(
        synchronize_session=False
    )
    db.query(KnowledgeMap).filter(KnowledgeMap.course_id == course_id).delete(
        synchronize_session=False
    )

    VectorStoreService().delete_by_course_id(course_id)

    db.delete(course)
    db.commit()
    logger.info("course.deleted course_id=%s doc_count=%d", course_id, len(document_ids))
    return success({"deleted_course_id": course_id}, message="Course deleted")
