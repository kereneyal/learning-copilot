from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine

from app.routes.courses import router as courses_router
from app.routes.lecturers import router as lecturers_router
from app.routes.lectures import router as lectures_router
from app.routes.documents import router as documents_router
from app.routes.summaries import router as summaries_router
from app.routes.qa import router as qa_router
from app.routes.course_summaries import router as course_summaries_router
from app.routes.knowledge_maps import router as knowledge_maps_router
from app.routes.copilot import router as copilot_router

from app.models.course import Course
from app.models.lecturer import Lecturer
from app.models.lecture import Lecture
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Learning Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(courses_router)
app.include_router(lecturers_router)
app.include_router(lectures_router)
app.include_router(documents_router)
app.include_router(summaries_router)
app.include_router(qa_router)
app.include_router(course_summaries_router)
app.include_router(knowledge_maps_router)
app.include_router(copilot_router)


@app.get("/")
def root():
    return {"message": "Learning Copilot API is running"}
