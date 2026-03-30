from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.global_search_service import search_everywhere

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/global")
def global_search(
    q: str,
    course_id: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    results = search_everywhere(
        db=db,
        q=q,
        course_id=course_id,
        limit=limit,
    )

    return {
        "query": q,
        "results": results
    }
