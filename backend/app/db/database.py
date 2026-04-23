import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# Read from DATABASE_URL env var; default keeps local-dev behaviour unchanged.
# For Docker: set DATABASE_URL in docker-compose.yml or the .env file.
# Note: SQLite works only with a single uvicorn worker (WEB_CONCURRENCY=1).
#       Migrate to PostgreSQL before increasing workers.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./learning_copilot.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def ensure_sqlite_schema():
    """
    Minimal SQLite schema evolution for local dev.
    SQLite + create_all() won't add new columns to existing tables.
    """
    try:
        with engine.begin() as conn:
            columns = conn.execute(text("PRAGMA table_info(documents)")).fetchall()
            existing = {row[1] for row in columns}  # row[1] is column name

            if "processing_progress" not in existing:
                conn.execute(text("ALTER TABLE documents ADD COLUMN processing_progress INTEGER DEFAULT 0"))
            if "error_type" not in existing:
                conn.execute(text("ALTER TABLE documents ADD COLUMN error_type TEXT"))
            if "error_stage" not in existing:
                conn.execute(text("ALTER TABLE documents ADD COLUMN error_stage TEXT"))
            if "summary_status" not in existing:
                conn.execute(text(
                    "ALTER TABLE documents ADD COLUMN summary_status TEXT DEFAULT 'not_started'"
                ))
            # Backfill: mark docs that already have a summary row as completed.
            conn.execute(text("""
                UPDATE documents
                SET summary_status = 'completed'
                WHERE id IN (SELECT document_id FROM summaries)
                  AND (summary_status IS NULL OR summary_status = 'not_started')
            """))
    except Exception as exc:
        # Best-effort — do not raise; a fresh DB will have all columns via
        # create_all(). Log at ERROR so the failure is visible in structured logs.
        logger.error(
            "db.schema_migration_failed error=%s — app will continue but the "
            "schema may be incomplete on existing databases",
            exc,
            exc_info=True,
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
