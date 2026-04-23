import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

# Configure structured logging before any other imports so every module's
# getLogger() call inherits the JSON formatter set here.
from app.core.logging_config import configure_logging

configure_logging()

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine, ensure_sqlite_schema
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.vector_store import VectorStoreService

# ── Route imports ──────────────────────────────────────────────────────────────
from app.routes.health import router as health_router
from app.routes.courses import router as courses_router
from app.routes.lecturers import router as lecturers_router
from app.routes.lectures import router as lectures_router
from app.routes.documents import router as documents_router
from app.routes.summaries import router as summaries_router
from app.routes.qa import router as qa_router
from app.routes.course_summaries import router as course_summaries_router
from app.routes.knowledge_maps import router as knowledge_maps_router
from app.routes.copilot import router as copilot_router
from app.routes.search import router as search_router
from app.routes.question_image import router as question_image_router
from app.routes.debug import router as debug_router
from app.routes import syllabus, ai_study, exam

# ── Model imports (ensure tables exist before create_all) ─────────────────────
from app.models.course import Course  # noqa: F401
from app.models.lecturer import Lecturer  # noqa: F401
from app.models.lecture import Lecture  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.summary import Summary  # noqa: F401
from app.models.course_summary import CourseSummary  # noqa: F401
from app.models.knowledge_map import KnowledgeMap  # noqa: F401
from app.models.exam_question import ExamQuestion  # noqa: F401
from app.models.exam_simulation import ExamSimulation  # noqa: F401
from app.models.exam_simulation_question import ExamSimulationQuestion  # noqa: F401

logger = logging.getLogger(__name__)

# ── Schema setup (module level — must complete before routers register) ────────
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

# ── CORS origins ───────────────────────────────────────────────────────────────
_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the FastAPI application."""
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info(
        "startup.begin cors_origins=%s log_level=%s",
        _allowed_origins,
        os.getenv("LOG_LEVEL", "INFO"),
    )

    try:
        VectorStoreService().validate_embeddings_health()
        logger.info("startup.embeddings_ok")
    except Exception as exc:
        logger.warning("startup.embeddings_unavailable error=%s", exc)

    try:
        from app.agents.qa_agent import QAAgent

        QAAgent().validate_generation_health()
        logger.info("startup.generation_ok")
    except Exception as exc:
        logger.warning("startup.generation_unavailable error=%s", exc)

    logger.info("startup.complete")

    yield  # application runs here

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("shutdown.complete")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Learning Copilot API",
    description="AI-powered learning assistant — RAG Q&A, document processing, exam simulation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────
# Starlette processes middleware in LIFO order (last added = outermost).
# We want: CORS (outermost, handles preflight) → RequestLogging → App.
# So: add RequestLogging first, CORS second.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(courses_router)
app.include_router(lecturers_router)
app.include_router(lectures_router)
app.include_router(documents_router)
app.include_router(summaries_router)
app.include_router(qa_router)
app.include_router(course_summaries_router)
app.include_router(knowledge_maps_router)
app.include_router(copilot_router)
app.include_router(search_router)
app.include_router(question_image_router)
app.include_router(debug_router)
app.include_router(syllabus.router)
app.include_router(ai_study.router)
app.include_router(exam.router)


# ── Root ───────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Root"], include_in_schema=False)
def root():
    return {"message": "Learning Copilot API", "docs": "/docs", "health": "/health"}
