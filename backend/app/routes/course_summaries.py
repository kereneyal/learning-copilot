from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.agents.course_summary_agent import CourseSummaryAgent

router = APIRouter(prefix="/course-summaries", tags=["Course Summaries"])


@router.post("/course/{course_id}")
def summarize_course(course_id: str, db: Session = Depends(get_db)):
    documents = db.query(Document).filter(Document.course_id == course_id).all()

    if not documents:
        raise HTTPException(status_code=404, detail="No documents found for this course")

    document_ids = [doc.id for doc in documents]

    summaries = db.query(Summary).filter(Summary.document_id.in_(document_ids)).all()

    if not summaries:
        raise HTTPException(status_code=404, detail="No document summaries found for this course")

    summaries_texts = [summary.summary_text for summary in summaries]
    language = summaries[0].language or "en"

    agent = CourseSummaryAgent()
    course_summary_text = agent.summarize_course(summaries_texts, language)

    new_course_summary = CourseSummary(
        course_id=course_id,
        summary_text=course_summary_text,
        language=language
    )

    db.add(new_course_summary)
    db.commit()
    db.refresh(new_course_summary)

    return {
        "id": new_course_summary.id,
        "course_id": new_course_summary.course_id,
        "language": new_course_summary.language,
        "summary_text": new_course_summary.summary_text,
        "created_at": new_course_summary.created_at,
    }


@router.get("/course/{course_id}")
def get_course_summaries(course_id: str, db: Session = Depends(get_db)):
    summaries = db.query(CourseSummary).filter(CourseSummary.course_id == course_id).all()

    return [
        {
            "id": summary.id,
            "course_id": summary.course_id,
            "language": summary.language,
            "summary_text": summary.summary_text,
            "created_at": summary.created_at,
        }
        for summary in summaries
    ]
