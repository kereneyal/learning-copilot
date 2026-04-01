import chromadb
import requests
import time
import random


class EmbeddingError(Exception):
    pass


class VectorStoreWriteError(Exception):
    pass


class VectorStoreService:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.client.get_or_create_collection(name="course_chunks")
        self.ollama_base_url = "http://localhost:11434"
        self.embedding_model = "nomic-embed-text"

    def _embed_once(self, text, timeout_s: int = 60):
        response = requests.post(
            f"{self.ollama_base_url}/api/embeddings",
            json={
                "model": self.embedding_model,
                "prompt": text
            },
            timeout=timeout_s
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def _embed(self, text, max_attempts: int = 3, timeout_s: int = 60):
        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self._embed_once(text, timeout_s=timeout_s)
            except Exception as e:
                last_err = e
                if attempt >= max_attempts:
                    break
                backoff = min(2.0 ** (attempt - 1), 8.0) + random.uniform(0, 0.25)
                time.sleep(backoff)
        raise EmbeddingError(str(last_err) if last_err else "Embedding failed")

    def add_chunks(
        self,
        document_id,
        course_id,
        lecture_id,
        chunks,
        embed_attempts: int = 3,
        write_attempts: int = 3,
        stage_timeout_s: int = 60,
    ) -> int:
        if not chunks:
            return 0

        cleaned_chunks = []
        for c in chunks:
            if c is None:
                continue
            c = str(c)
            if c.strip():
                cleaned_chunks.append(c.strip())

        if not cleaned_chunks:
            return 0

        embeddings = [self._embed(chunk, max_attempts=embed_attempts, timeout_s=stage_timeout_s) for chunk in cleaned_chunks]
        ids = [f"{document_id}_{i}" for i in range(len(cleaned_chunks))]

        metadatas = []
        for i in range(len(cleaned_chunks)):
            metadatas.append({
                "document_id": document_id,
                "course_id": course_id,
                "lecture_id": lecture_id,
                "chunk_index": i
            })

        last_err = None
        for attempt in range(1, write_attempts + 1):
            try:
                self.collection.add(
                    ids=ids,
                    documents=cleaned_chunks,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt >= write_attempts:
                    break
                backoff = min(2.0 ** (attempt - 1), 8.0) + random.uniform(0, 0.25)
                time.sleep(backoff)

        if last_err is not None:
            raise VectorStoreWriteError(str(last_err))
        return len(ids)

    def _build_where(self, course_id=None, lecture_id=None):
        if lecture_id and course_id:
            return {"$and": [{"course_id": course_id}, {"lecture_id": lecture_id}]}
        if course_id:
            return {"course_id": course_id}
        if lecture_id:
            return {"lecture_id": lecture_id}
        return None

    def fetch_chunks_for_scope(self, course_id, lecture_id=None, limit=800):
        """
        Pull chunk texts for lexical scoring (bounded). Requires course_id.
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
        except Exception:
            return []

        docs = batch.get("documents") or []
        metas = batch.get("metadatas") or []
        out = []
        for doc, meta in zip(docs, metas):
            if meta is None:
                meta = {}
            out.append({"text": doc or "", "metadata": meta})
        return out

    def search_with_distances(self, query, course_id=None, lecture_id=None, top_k=12):
        embedding = self._embed(query, max_attempts=3, timeout_s=60)
        where = self._build_where(course_id=course_id, lecture_id=lecture_id)

        q_kwargs = dict(
            query_embeddings=[embedding],
            n_results=top_k,
        )
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
            chunks.append({
                "text": doc,
                "snippet": doc[:300] if doc else "",
                "course_id": meta.get("course_id") if meta else None,
                "lecture_id": meta.get("lecture_id") if meta else None,
                "document_id": meta.get("document_id") if meta else None,
                "chunk_index": meta.get("chunk_index") if meta else None,
                "_distance": dist,
            })
        return chunks

    def search(self, query, course_id=None, lecture_id=None, top_k=12):
        chunks = self.search_with_distances(
            query=query,
            course_id=course_id,
            lecture_id=lecture_id,
            top_k=top_k,
        )
        for c in chunks:
            c.pop("_distance", None)
        return chunks

    def delete_by_course_id(self, course_id):
        try:
            items = self.collection.get(where={"course_id": course_id})
            ids = items.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as e:
            print(f"delete_by_course_id warning: {e}")

    def delete_by_lecture_id(self, lecture_id):
        try:
            items = self.collection.get(where={"lecture_id": lecture_id})
            ids = items.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as e:
            print(f"delete_by_lecture_id warning: {e}")

    def delete_by_document_id(self, document_id):
        try:
            items = self.collection.get(where={"document_id": document_id})
            ids = items.get("ids", []) or []
            if ids:
                self.collection.delete(ids=ids)
        except Exception as e:
            print(f"delete_by_document_id warning: {e}")
