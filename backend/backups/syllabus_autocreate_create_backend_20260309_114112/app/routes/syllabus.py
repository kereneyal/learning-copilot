import os
import shutil

from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.agents.ingestion_agent import IngestionAgent
from app.agents.syllabus_parser_agent import SyllabusParserAgent

router = APIRouter(prefix="/syllabus", tags=["Syllabus"])

UPLOAD_DIR = "storage/syllabus"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/preview")
def preview_syllabus(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    file_extension = file.filename.split(".")[-1].lower()

    saved_file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion_agent = IngestionAgent()

    extracted_text = ingestion_agent.extract_text(
        saved_file_path,
        file_extension
    )

    parser = SyllabusParserAgent()

    structured_data = parser.parse(extracted_text)

    return {
        "file_name": file.filename,
        "parsed": structured_data,
        "text_preview": extracted_text[:2000]
    }
