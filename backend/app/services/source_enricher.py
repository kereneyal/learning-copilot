from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.lecture import Lecture
from app.models.document import Document


def enrich_sources(db: Session, raw_sources):
    enriched = []

    for source in raw_sources:
        course_id = source.get("course_id")
        lecture_id = source.get("lecture_id")
        document_id = source.get("document_id")

        course = None
        lecture = None
        document = None

        if course_id:
            course = db.query(Course).filter(Course.id == course_id).first()

        if lecture_id:
            lecture = db.query(Lecture).filter(Lecture.id == lecture_id).first()

        if document_id:
            document = db.query(Document).filter(Document.id == document_id).first()

        enriched.append({
            "course_id": course_id,
            "course_name": course.name if course else None,
            "lecture_id": lecture_id,
            "lecture_title": lecture.title if lecture else None,
            "document_id": document_id,
            "document_name": document.file_name if document else None,
            "snippet": source.get("snippet"),
            "chunk_index": source.get("chunk_index"),
        })

    return enriched
