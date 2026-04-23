"""
Vector store service wrapping ChromaDB + Ollama embeddings.

Key safety guarantees:
- Embeddings are computed BEFORE old chunks are deleted.  If embedding fails
  mid-batch the existing data in Chroma is untouched.
- Chunks are written in a single atomic Chroma `add()` call.  Partial writes
  cannot occur.
- Parallel embedding (ThreadPoolExecutor) cuts ingestion time significantly
  without changing the Ollama API endpoint.
- fetch_chunks_for_scope warns when the result set hits the fetch ceiling so
  operators know lexical retrieval may be incomplete.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import random
import time
from typing import List, Optional

import chromadb
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding concurrency — CPU-only Ollama has a single runner thread, so
# parallel workers create a queue: the 4th request waits for 3 others to
# finish before Ollama even starts it.  Default = 1 (serial) eliminates that
# contention.  Raise for GPU-backed or API-backed Ollama instances.
# ---------------------------------------------------------------------------
_EMBED_WORKERS: int = int(os.getenv("EMBED_WORKERS", "1"))

# Per-request HTTP timeout for a single embedding call.
# nomic-embed-text on a warm CPU runner: 1–5 s; cold start: up to 30 s.
# 90 s gives a large safety margin without being so long that a genuinely
# dead Ollama hangs ingestion for more than ~5 min (3 retries × 90 s).
_EMBED_SINGLE_TIMEOUT_S: int = int(os.getenv("EMBED_SINGLE_TIMEOUT_S", "90"))


class EmbeddingError(Exception):
    pass


class VectorStoreWriteError(Exception):
    pass


class VectorStoreService:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.client.get_or_create_collection(name="course_chunks")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        configured_endpoint = os.getenv("OLLAMA_EMBEDDING_ENDPOINT", "/api/embed")
        if configured_endpoint == "/api/embeddings":
            logger.error(
                "ollama.embedding_endpoint_legacy_configured endpoint=%s "
                "message='Ollama embeddings moved to /api/embed; using current endpoint'",
                configured_endpoint,
            )
            configured_endpoint = "/api/embed"
        self.embedding_endpoint = configured_endpoint

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _embed_once(self, text: str, timeout_s: int = _EMBED_SINGLE_TIMEOUT_S) -> list:
        endpoint = f"{self.ollama_base_url}{self.embedding_endpoint}"
        t0 = time.monotonic()
        logger.debug(
            "ollama.embed_request endpoint=%s model=%s text_len=%d timeout_s=%d",
            endpoint,
            self.embedding_model,
            len(text),
            timeout_s,
        )
        response = requests.post(
            endpoint,
            json={"model": self.embedding_model, "input": text},
            timeout=timeout_s,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if response.status_code >= 400:
            logger.error(
                "ollama.embedding_failed endpoint=%s model=%s status_code=%s "
                "elapsed_ms=%d body=%s",
                endpoint,
                self.embedding_model,
                response.status_code,
                elapsed_ms,
                self._short_error_body(response),
            )
        else:
            logger.info(
                "ollama.embed_response endpoint=%s model=%s status_code=%s elapsed_ms=%d",
                endpoint,
                self.embedding_model,
                response.status_code,
                elapsed_ms,
            )
        response.raise_for_status()
        return self._parse_embedding_response(response.json())

    def _parse_embedding_response(self, data: dict) -> list:
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            first = embeddings[0]
            if isinstance(first, list):
                return first

        legacy_embedding = data.get("embedding")
        if isinstance(legacy_embedding, list):
            return legacy_embedding

        raise EmbeddingError("Ollama embedding response did not contain embeddings")

    def _short_error_body(self, response, limit: int = 300) -> str:
        body = getattr(response, "text", "") or ""
        body = " ".join(body.split())
        return body[:limit]

    def validate_embeddings_health(self, timeout_s: int = 10) -> bool:
        try:
            embedding = self._embed_once("health check", timeout_s=timeout_s)
            logger.info(
                "ollama.embedding_health_ok endpoint=%s model=%s dimensions=%d",
                f"{self.ollama_base_url}{self.embedding_endpoint}",
                self.embedding_model,
                len(embedding),
            )
            return True
        except Exception as e:
            logger.error(
                "ollama.embedding_health_failed endpoint=%s model=%s error=%s",
                f"{self.ollama_base_url}{self.embedding_endpoint}",
                self.embedding_model,
                e,
            )
            return False

    def _embed(self, text: str, max_attempts: int = 3, timeout_s: int = _EMBED_SINGLE_TIMEOUT_S) -> list:
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self._embed_once(text, timeout_s=timeout_s)
            except Exception as e:
                last_err = e
                if attempt >= max_attempts:
                    break
                backoff = min(2.0 ** (attempt - 1), 8.0) + random.uniform(0, 0.25)
                logger.warning(
                    "ollama.embed_retry attempt=%d/%d backoff_s=%.1f error=%s",
                    attempt, max_attempts, backoff, e,
                )
                time.sleep(backoff)
        raise EmbeddingError(str(last_err) if last_err else "Embedding failed")

    def _embed_parallel(
        self,
        texts: List[str],
        max_attempts: int = 3,
        timeout_s: int = _EMBED_SINGLE_TIMEOUT_S,
    ) -> List[list]:
        """
        Embed a list of texts using a thread pool.

        Serial by default (EMBED_WORKERS=1) to avoid Ollama queue contention on
        CPU-only machines — parallel workers do not help when Ollama serialises
        requests internally.  Raise EMBED_WORKERS for GPU-backed instances.

        All embeddings are computed before any write to Chroma occurs.  If any
        single chunk fails after all retries the whole batch raises immediately,
        preventing a partial write later.
        """
        n = len(texts)
        results: List[Optional[list]] = [None] * n
        completed = 0

        logger.info(
            "vector_store.embed_parallel_start chunks=%d workers=%d timeout_s=%d",
            n,
            _EMBED_WORKERS,
            timeout_s,
        )

        def _embed_indexed(idx_text):
            idx, text = idx_text
            return idx, self._embed(text, max_attempts=max_attempts, timeout_s=timeout_s)

        with concurrent.futures.ThreadPoolExecutor(max_workers=_EMBED_WORKERS) as pool:
            futures = {
                pool.submit(_embed_indexed, (i, t)): i
                for i, t in enumerate(texts)
            }
            for fut in concurrent.futures.as_completed(futures):
                idx, embedding = fut.result()  # raises on embed failure
                results[idx] = embedding
                completed += 1
                logger.info(
                    "vector_store.embed_progress done=%d/%d remaining=%d",
                    completed,
                    n,
                    n - completed,
                )

        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def add_chunks(
        self,
        document_id: str,
        course_id: str,
        lecture_id: Optional[str],
        chunks: List[str],
        embed_attempts: int = 3,
        write_attempts: int = 3,
        embed_timeout_s: int = _EMBED_SINGLE_TIMEOUT_S,
    ) -> int:
        """
        Embed all chunks then write them to Chroma in one atomic call.

        embed_timeout_s is the per-request HTTP timeout for each individual
        Ollama call — NOT a stage-level wall clock.  The caller is responsible
        for any higher-level timeout policy (or none at all for slow CPU runs).

        Safety order:
          1. Clean + validate input texts.
          2. Embed ALL chunks (fail fast if any chunk fails — no data deleted yet).
          3. Delete existing chunks for this document.
          4. Write new embeddings (retry on transient Chroma errors).
          5. Verify written count matches expected count.

        Returns the number of chunks indexed.
        """
        if not chunks:
            return 0

        cleaned: List[str] = [
            str(c).strip() for c in chunks if c is not None and str(c).strip()
        ]
        if not cleaned:
            return 0

        n = len(cleaned)
        logger.info(
            "vector_store.embed_start doc_id=%s course_id=%s chunks=%d embed_timeout_s=%d",
            document_id,
            course_id,
            n,
            embed_timeout_s,
        )

        # Step 1 — embed everything before touching existing data.
        t0 = time.monotonic()
        embeddings = self._embed_parallel(
            cleaned,
            max_attempts=embed_attempts,
            timeout_s=embed_timeout_s,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "vector_store.embed_done doc_id=%s chunks=%d elapsed_ms=%d avg_ms_per_chunk=%d",
            document_id,
            n,
            elapsed_ms,
            elapsed_ms // n if n else 0,
        )

        ids = [f"{document_id}_{i}" for i in range(n)]
        metadatas = [
            {
                "document_id": document_id,
                "course_id": course_id,
                "lecture_id": lecture_id,
                "chunk_index": i,
            }
            for i in range(n)
        ]

        # Step 2 — delete old chunks only after embeddings are ready.
        try:
            self.delete_by_document_id(document_id)
        except Exception as e:
            logger.warning(
                "vector_store.pre_write_delete_failed doc_id=%s error=%s — proceeding",
                document_id,
                e,
            )

        # Step 3 — write in one atomic call.
        last_err = None
        for attempt in range(1, write_attempts + 1):
            try:
                self.collection.add(
                    ids=ids,
                    documents=cleaned,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt >= write_attempts:
                    break
                backoff = min(2.0 ** (attempt - 1), 8.0) + random.uniform(0, 0.25)
                logger.warning(
                    "vector_store.write_retry doc_id=%s attempt=%d error=%s",
                    document_id,
                    attempt,
                    e,
                )
                time.sleep(backoff)

        if last_err is not None:
            raise VectorStoreWriteError(str(last_err))

        # Step 4 — verify the write landed completely.
        actual = self.count_chunks_for_document(document_id)
        if actual != n:
            raise VectorStoreWriteError(
                f"Write verification failed for doc_id={document_id}: "
                f"expected {n} chunks, found {actual} in Chroma."
            )

        logger.info(
            "vector_store.write_verified doc_id=%s expected=%d actual=%d",
            document_id,
            n,
            actual,
        )
        return n

    # ------------------------------------------------------------------
    # Read / query helpers
    # ------------------------------------------------------------------

    def count_chunks_for_document(self, document_id: str) -> int:
        """Return the number of chunks currently stored for a document."""
        try:
            result = self.collection.get(
                where={"document_id": document_id},
                include=[],
            )
            return len(result.get("ids") or [])
        except Exception as e:
            logger.warning(
                "vector_store.count_failed doc_id=%s error=%s", document_id, e
            )
            return 0

    def _build_where(self, course_id=None, lecture_id=None):
        if lecture_id and course_id:
            return {"$and": [{"course_id": course_id}, {"lecture_id": lecture_id}]}
        if course_id:
            return {"course_id": course_id}
        if lecture_id:
            return {"lecture_id": lecture_id}
        return None

    def fetch_chunks_for_scope(
        self, course_id: str, lecture_id: Optional[str] = None, limit: int = 1500
    ) -> list:
        """
        Pull chunk texts for lexical scoring (bounded by limit).
        Logs a warning when the result set is capped so operators can detect
        under-retrieval on large courses.
        """
        if not course_id:
            return []

        where = self._build_where(course_id=course_id, lecture_id=lecture_id)
        try:
            batch = self.collection.get(
                where=where,
                limit=limit,
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.warning(
                "vector_store.fetch_chunks_failed course_id=%s error=%s", course_id, e
            )
            return []

        docs = batch.get("documents") or []
        metas = batch.get("metadatas") or []
        out = []
        for doc, meta in zip(docs, metas):
            if meta is None:
                meta = {}
            out.append({"text": doc or "", "metadata": meta})

        if len(out) >= limit:
            logger.warning(
                "vector_store.fetch_at_limit course_id=%s fetched=%d limit=%d "
                "— some chunks may not appear in lexical retrieval",
                course_id,
                len(out),
                limit,
            )

        return out

    def search_with_distances(
        self,
        query: str,
        course_id: Optional[str] = None,
        lecture_id: Optional[str] = None,
        top_k: int = 12,
    ) -> list:
        embedding = self._embed(query, max_attempts=3, timeout_s=60)
        where = self._build_where(course_id=course_id, lecture_id=lecture_id)

        q_kwargs = dict(query_embeddings=[embedding], n_results=top_k)
        if where:
            q_kwargs["where"] = where

        try:
            results = self.collection.query(
                **q_kwargs,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            results = self.collection.query(**q_kwargs)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if results.get("distances") else []

        chunks = []
        for i, (doc, meta) in enumerate(zip(documents, metadatas)):
            dist = distances[i] if i < len(distances) else None
            chunks.append(
                {
                    "text": doc,
                    "snippet": doc[:300] if doc else "",
                    "course_id": meta.get("course_id") if meta else None,
                    "lecture_id": meta.get("lecture_id") if meta else None,
                    "document_id": meta.get("document_id") if meta else None,
                    "chunk_index": meta.get("chunk_index") if meta else None,
                    "_distance": dist,
                }
            )
        return chunks

    def search(
        self,
        query: str,
        course_id: Optional[str] = None,
        lecture_id: Optional[str] = None,
        top_k: int = 12,
    ) -> list:
        chunks = self.search_with_distances(
            query=query, course_id=course_id, lecture_id=lecture_id, top_k=top_k
        )
        for c in chunks:
            c.pop("_distance", None)
        return chunks

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    def delete_by_course_id(self, course_id: str) -> None:
        try:
            items = self.collection.get(where={"course_id": course_id})
            ids = items.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as e:
            logger.warning("vector_store.delete_by_course_id warning: %s", e)

    def delete_by_lecture_id(self, lecture_id: str) -> None:
        try:
            items = self.collection.get(where={"lecture_id": lecture_id})
            ids = items.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as e:
            logger.warning("vector_store.delete_by_lecture_id warning: %s", e)

    def delete_by_document_id(self, document_id: str) -> None:
        try:
            items = self.collection.get(where={"document_id": document_id})
            ids = items.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as e:
            logger.warning("vector_store.delete_by_document_id warning: %s", e)
