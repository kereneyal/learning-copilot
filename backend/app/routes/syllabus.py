import os
import re
import shutil
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.agents.ingestion_agent import IngestionAgent
from app.agents.syllabus_parser_agent import SyllabusParserAgent

from app.models.course import Course
from app.models.lecturer import Lecturer
from app.models.lecture import Lecture
from app.models.document import Document

router = APIRouter(prefix="/syllabus", tags=["Syllabus"])

UPLOAD_DIR = "storage/syllabus"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ParsedLecturer(BaseModel):
    full_name: str
    bio: Optional[str] = None


class ParsedLecture(BaseModel):
    title: str
    lecture_date: Optional[str] = None
    lecturer_name: Optional[str] = None
    notes: Optional[str] = None


class ParsedCoursePayload(BaseModel):
    course_name: str
    institution: Optional[str] = None
    semester: Optional[str] = None
    language: Optional[str] = "en"
    lecturers: List[ParsedLecturer] = []
    lectures: List[ParsedLecture] = []
    syllabus_file_name: Optional[str] = None
    syllabus_file_path: Optional[str] = None
    syllabus_raw_text: Optional[str] = None


@router.post("/preview")
def preview_syllabus(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    safe_filename = os.path.basename(file.filename)
    safe_filename = re.sub(r"[^A-Za-z0-9._\-א-ת ]", "_", safe_filename)

    file_extension = safe_filename.split(".")[-1].lower() if "." in safe_filename else "txt"
    saved_file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion_agent = IngestionAgent()
    extracted_text = ingestion_agent.extract_text(saved_file_path, file_extension)

    parser = SyllabusParserAgent()
    structured_data = parser.parse(extracted_text)

    return {
        "file_name": safe_filename,
        "file_path": saved_file_path,
        "parsed": structured_data,
        "text_preview": extracted_text[:2000],
        "raw_text": extracted_text,
    }


@router.post("/create-course")
def create_course_from_syllabus(
    payload: ParsedCoursePayload,
    db: Session = Depends(get_db)
):
    if not payload.course_name.strip():
        raise HTTPException(status_code=400, detail="course_name is required")

    course = Course(
        name=payload.course_name,
        institution=payload.institution,
        semester=payload.semester,
        default_language=payload.language or "en",
    )

    db.add(course)
    db.commit()
    db.refresh(course)

    lecturer_map = {}

    for lecturer_payload in payload.lecturers:
        full_name = (lecturer_payload.full_name or "").strip()
        if not full_name:
            continue

        existing = db.query(Lecturer).filter(Lecturer.full_name == full_name).first()

        if existing:
            lecturer_map[full_name] = existing
            continue

        lecturer = Lecturer(
            full_name=full_name,
            bio=lecturer_payload.bio
        )
        db.add(lecturer)
        db.commit()
        db.refresh(lecturer)

        lecturer_map[full_name] = lecturer

    created_lectures = []

    for lecture_payload in payload.lectures:
        lecturer_id = None

        lecturer_name = (lecture_payload.lecturer_name or "").strip()
        if lecturer_name and lecturer_name in lecturer_map:
            lecturer_id = lecturer_map[lecturer_name].id
        elif lecturer_map:
            lecturer_id = list(lecturer_map.values())[0].id

        if not lecture_payload.title.strip():
            continue

        lecture = Lecture(
            course_id=course.id,
            lecturer_id=lecturer_id,
            title=lecture_payload.title,
            lecture_date=lecture_payload.lecture_date,
            notes=lecture_payload.notes,
        )

        db.add(lecture)
        db.commit()
        db.refresh(lecture)

        created_lectures.append({
            "id": lecture.id,
            "title": lecture.title,
            "lecture_date": lecture.lecture_date,
            "lecturer_id": lecture.lecturer_id,
        })

    created_document = None

    if payload.syllabus_file_name and payload.syllabus_file_path:
        document = Document(
            course_id=course.id,
            file_name=payload.syllabus_file_name,
            file_path=payload.syllabus_file_path,
            file_type=payload.syllabus_file_name.split(".")[-1].lower() if "." in payload.syllabus_file_name else "txt",
            language=payload.language or "en",
            source_type="syllabus",
            topic="Course syllabus",
            raw_text=payload.syllabus_raw_text,		
        )

        if hasattr(document, "processing_status"):
            setattr(document, "processing_status", "ready")

        db.add(document)
        db.commit()
        db.refresh(document)

        created_document = {
            "id": document.id,
            "file_name": document.file_name,
            "source_type": document.source_type,
        }

    return {
        "status": "created",
        "course": {
            "id": course.id,
            "name": course.name,
            "institution": course.institution,
            "semester": course.semester,
            "default_language": getattr(course, "default_language", None),
        },
        "lecturers": [
            {
                "id": lecturer.id,
                "full_name": lecturer.full_name,
            }
            for lecturer in lecturer_map.values()
        ],
        "lectures": created_lectures,
        "syllabus_document": created_document,
    }
