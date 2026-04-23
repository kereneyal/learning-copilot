#!/usr/bin/env python3
"""
Re-embed all documents in Chroma using the current /api/embed endpoint.

Run from backend/ directory:
    python3 scripts/reindex_all.py

This script reads raw_text from SQLite, re-chunks it, and re-embeds it using
the current vector store configuration. Run this whenever the embedding endpoint
or model changes.
"""
import os
import sys
import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("reindex")

from app.db.database import SessionLocal
from app.models.document import Document
from app.agents.chunking_agent import ChunkingAgent
import app.services.vector_store as _vs_module
# CPU-only Ollama: serial embedding avoids queue contention that causes timeouts
_vs_module._EMBED_WORKERS = 1
from app.services.vector_store import VectorStoreService


def main():
    db = SessionLocal()
    vs = VectorStoreService()

    logger.info(
        "Config: embedding_model=%s endpoint=%s%s generation_model=%s",
        vs.embedding_model,
        vs.ollama_base_url,
        vs.embedding_endpoint,
        os.getenv("OLLAMA_GENERATION_MODEL", "llama3:latest"),
    )

    logger.info("Verifying embedding endpoint health...")
    ok = vs.validate_embeddings_health(timeout_s=15)
    if not ok:
        logger.error("Embedding health check failed — aborting. Is Ollama running?")
        sys.exit(1)

    docs = (
        db.query(Document)
        .filter(Document.raw_text != None, Document.raw_text != "")
        .all()
    )
    logger.info("Found %d documents with raw_text to re-index.", len(docs))

    chunker = ChunkingAgent(max_chunk_size=1200, overlap_size=200)

    success = 0
    failed = 0
    total_chunks = 0

    for i, doc in enumerate(docs, 1):
        logger.info(
            "[%d/%d] Re-indexing doc_id=%s lecture_id=%s text_len=%d",
            i, len(docs), doc.id, doc.lecture_id, len(doc.raw_text),
        )
        try:
            chunks = chunker.chunk_text(doc.raw_text)
            if not chunks:
                logger.warning("  doc_id=%s produced 0 chunks — skipping", doc.id)
                continue

            n = vs.add_chunks(
                document_id=str(doc.id),
                course_id=str(doc.course_id),
                lecture_id=str(doc.lecture_id) if doc.lecture_id else None,
                chunks=chunks,
                stage_timeout_s=600,  # 4 workers × ~120s/embed = up to 480s queue wait
            )
            total_chunks += n
            success += 1
            logger.info("  doc_id=%s -> %d chunks indexed", doc.id, n)
        except Exception as exc:
            failed += 1
            logger.error("  FAILED doc_id=%s error=%s", doc.id, exc)

    db.close()
    logger.info(
        "Re-indexing complete. success=%d failed=%d total_chunks=%d",
        success, failed, total_chunks,
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
