from fastapi import APIRouter
from app.schemas.ai_study import AIStudyRequest, AIStudyResponse
from app.services.ai_study_service import AIStudyService

router = APIRouter(prefix="/ai", tags=["AI Study"])

service = AIStudyService()


@router.post("/study", response_model=AIStudyResponse)
def generate_study_content(payload: AIStudyRequest):
    return service.generate(payload.text, payload.mode)
