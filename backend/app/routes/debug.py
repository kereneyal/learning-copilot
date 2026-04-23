"""
Debug / diagnostic endpoints.

All routes are gated behind DEBUG_RETRIEVAL=1 (or "true") env var so they
are never reachable in production unless explicitly opted in.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.vector_store import VectorStoreService
from app.services.hybrid_qa_retrieval import hybrid_retrieve_for_qa

router = APIRouter(prefix="/debug", tags=["Debug"])

_DEBUG_ENABLED = os.getenv("DEBUG_RETRIEVAL", "").lower() in ("1", "true", "yes")


def _require_debug():
    if not _DEBUG_ENABLED:
        raise HTTPException(
            status_code=403,
            detail=(
                "Debug endpoints are disabled. "
                "Set DEBUG_RETRIEVAL=1 in the server environment to enable."
            ),
        )


class RetrievalDebugRequest(BaseModel):
    question: str
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None


@router.post("/retrieval")
def debug_retrieval(req: RetrievalDebugRequest, _: Session = Depends(get_db)):
    """
    Run the full hybrid retrieval pipeline for a question and return the
    internal scoring data (rerank scores, lexical/vector components, snippets).

    Useful for diagnosing wrong answers, domain-gate drops, and score
    distribution problems without going through the full QA agent.

    Only available when DEBUG_RETRIEVAL=1.
    """
    _require_debug()

    vs = VectorStoreService()
    # return_scores=True keeps _rerank_score / _lex / _dist on each chunk.
    chunks, abstain, reason = hybrid_retrieve_for_qa(
        vs,
        question=req.question,
        course_id=req.course_id,
        lecture_id=req.lecture_id,
        return_scores=True,
    )

    return {
        "question": req.question,
        "course_id": req.course_id,
        "lecture_id": req.lecture_id,
        "abstain": abstain,
        "abstain_reason": reason,
        "chunks_returned": len(chunks),
        "chunks": [
            {
                "rank": i,
                "document_id": c.get("document_id"),
                "chunk_index": c.get("chunk_index"),
                "rerank_score": round(float(c.get("_rerank_score") or 0), 4),
                "lex_raw": round(float(c.get("_lex") or 0), 4),
                "vec_distance": c.get("_dist"),
                "text_preview": (c.get("text") or "")[:300],
            }
            for i, c in enumerate(chunks)
        ],
    }


@router.get("/vector-store/course/{course_id}")
def debug_vector_store_stats(course_id: str, lecture_id: Optional[str] = None):
    """
    Return chunk counts for a course (and optionally a lecture) in Chroma.

    Useful for detecting partial-embedding failures: compare 'total_chunks'
    against the expected number from the document processing log.

    Only available when DEBUG_RETRIEVAL=1.
    """
    _require_debug()

    vs = VectorStoreService()
    # Fetch with a very high limit to get the true count.
    all_chunks = vs.fetch_chunks_for_scope(
        course_id=course_id,
        lecture_id=lecture_id,
        limit=50_000,
    )

    # Group by document_id so we can spot partially-embedded documents.
    by_doc: dict = {}
    for c in all_chunks:
        meta = c.get("metadata") or {}
        doc_id = meta.get("document_id", "unknown")
        by_doc[doc_id] = by_doc.get(doc_id, 0) + 1

    return {
        "course_id": course_id,
        "lecture_id": lecture_id,
        "total_chunks": len(all_chunks),
        "documents": [
            {"document_id": doc_id, "chunk_count": count}
            for doc_id, count in sorted(by_doc.items())
        ],
    }
