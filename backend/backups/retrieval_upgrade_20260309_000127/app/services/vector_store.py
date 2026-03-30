import chromadb
import requests


class VectorStoreService:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.client.get_or_create_collection(name="course_chunks")
        self.ollama_base_url = "http://localhost:11434"
        self.embedding_model = "nomic-embed-text"

    def _embed_texts(self, texts):
        embeddings = []

        for text in texts:
            response = requests.post(
                f"{self.ollama_base_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": text
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data["embedding"])

        return embeddings

    def add_chunks(self, document_id: str, course_id: str, chunks):
        if not chunks:
            return

        embeddings = self._embed_texts(chunks)

        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "course_id": course_id,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas
        )

    def search_chunks(self, course_id: str, query: str, top_k: int = 12):
        query_embedding = self._embed_texts([query])[0]

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"course_id": course_id}
        )

        return results

    def keyword_search(self, course_id: str, query: str, top_k: int = 5):
        try:
            items = self.collection.get(where={"course_id": course_id})
        except Exception:
            return {"documents": [[]], "metadatas": [[]]}

        docs = items.get("documents", []) or []
        metas = items.get("metadatas", []) or []

        query_terms = [t.strip().lower() for t in query.split() if t.strip()]
        scored = []

        for doc, meta in zip(docs, metas):
            score = 0
            lowered = doc.lower()
            for term in query_terms:
                if term in lowered:
                    score += 1
            if score > 0:
                scored.append((score, doc, meta))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        return {
            "documents": [[x[1] for x in top]],
            "metadatas": [[x[2] for x in top]],
        }
