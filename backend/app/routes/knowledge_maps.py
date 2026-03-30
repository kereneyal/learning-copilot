from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.knowledge_map import KnowledgeMap

router = APIRouter(prefix="/knowledge-maps", tags=["Knowledge Maps"])


@router.get("/course/{course_id}")
def get_latest_knowledge_map(course_id: str, db: Session = Depends(get_db)):
    km = (
        db.query(KnowledgeMap)
        .filter(KnowledgeMap.course_id == course_id)
        .order_by(KnowledgeMap.created_at.desc())
        .first()
    )

    if not km:
        raise HTTPException(status_code=404, detail="No knowledge map found")

    return {
        "id": km.id,
        "course_id": km.course_id,
        "language": km.language,
        "map_text": km.map_text,
        "created_at": km.created_at,
    }
