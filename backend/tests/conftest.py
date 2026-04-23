"""
Shared pytest fixtures for the Learning Copilot test suite.

Optional native packages (pptx, pytesseract, chromadb, etc.) are stubbed at
the top of this file so subsystem modules can be imported without requiring a
full system install. Integration tests that need real deps should be marked
@pytest.mark.integration and run in a complete environment.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies early, before any app module is imported.
# ---------------------------------------------------------------------------

def _stub(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


_stub("pptx", Presentation=MagicMock())
_stub("pptx.util", Inches=MagicMock(), Pt=MagicMock())
_stub("docx", Document=MagicMock())
_stub("pytesseract")
_stub("PIL", Image=MagicMock())
_stub("PIL.Image", open=MagicMock())

# chromadb -- prevents PersistentClient from touching the filesystem.
_chroma_col = MagicMock()
_chroma_client = MagicMock()
_chroma_client.get_or_create_collection.return_value = _chroma_col
_stub("chromadb", PersistentClient=MagicMock(return_value=_chroma_client))

_stub("openai", OpenAI=MagicMock())
_stub("sentence_transformers")

# Patch FastAPI's multipart guard so routes with Form/File params can be
# imported without python-multipart installed in the test environment.
try:
    import fastapi.dependencies.utils as _fdu
    _fdu.ensure_multipart_is_installed = lambda: None
except Exception:
    pass

# fitz (PyMuPDF) -- individual tests patch what they need.
_fitz = _stub("fitz")
_fitz.open = MagicMock()

# ---------------------------------------------------------------------------
# Now safe to import app modules.
# ---------------------------------------------------------------------------

from app.db.database import Base  # noqa: E402

TEST_DATABASE_URL = "sqlite:///:memory:"
_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db():
    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def mock_vector_store():
    vs = MagicMock()
    vs.fetch_chunks_for_scope.return_value = []
    vs.search_with_distances.return_value = []
    vs.add_chunks.return_value = 0
    vs.count_chunks_for_document.return_value = 0
    vs.delete_by_document_id.return_value = None
    return vs


def make_chunk(
    text: str,
    document_id: str = "doc-1",
    chunk_index: int = 0,
    course_id: str = "course-1",
    lecture_id: str | None = None,
    distance: float = 0.2,
) -> dict:
    return {
        "text": text,
        "snippet": text[:300],
        "document_id": document_id,
        "chunk_index": chunk_index,
        "course_id": course_id,
        "lecture_id": lecture_id,
        "_distance": distance,
        "_lex": 0.0,
    }
