from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text

DATABASE_URL = "sqlite:///./learning_copilot.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

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
    except Exception:
        # Best-effort; if this fails, the app may still run on fresh DBs.
        pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
