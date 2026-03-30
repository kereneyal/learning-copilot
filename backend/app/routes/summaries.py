from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.summary import Summary
from app.agents.summary_agent import SummaryAgent

router = APIRouter(prefix="/summaries", tags=["Summaries"])


@router.post("/document/{document_id}")
def summarize_document(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.raw_text:
        raise HTTPException(status_code=400, detail="Document has no extracted text")

    summary_agent = SummaryAgent()
    summary_text = summary_agent.summarize(document.raw_text, document.language or "en")

    new_summary = Summary(
        document_id=document.id,
        summary_text=summary_text,
        language=document.language
    )

    db.add(new_summary)
    db.commit()
    db.refresh(new_summary)

    return {
        "id": new_summary.id,
        "document_id": new_summary.document_id,
        "language": new_summary.language,
        "summary_text": new_summary.summary_text,
        "created_at": new_summary.created_at,
    }


@router.get("/document/{document_id}")
def get_document_summaries(document_id: str, db: Session = Depends(get_db)):
    summaries = db.query(Summary).filter(Summary.document_id == document_id).all()

    return [
        {
            "id": summary.id,
            "document_id": summary.document_id,
            "language": summary.language,
            "summary_text": summary.summary_text,
            "created_at": summary.created_at,
        }
        for summary in summaries
    ]
