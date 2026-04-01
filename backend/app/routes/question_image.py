import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.question_image_extractor import extract_question_from_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["Questions"])


@router.post("/extract-from-image")
async def extract_from_image(file: UploadFile = File(...)):
    """
    OCR-style extraction from a question screenshot, then multiple-choice parsing.
    Requires OPENAI_API_KEY for vision. Does not persist the image.
    """
    try:
        data = await file.read()
    except Exception as e:
        logger.warning("extract_from_image: read failed: %s", e)
        raise HTTPException(status_code=400, detail="Could not read upload") from e

    result = extract_question_from_image(data, file.filename or "image.png")

    if not result["success"]:
        detail = result.get("error") or "Extraction failed"
        if detail.startswith("OPENAI_API_KEY"):
            code = 503
        else:
            code = 400
        raise HTTPException(status_code=code, detail=detail)

    return result
