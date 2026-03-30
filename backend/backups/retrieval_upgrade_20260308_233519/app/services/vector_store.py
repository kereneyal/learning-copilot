import chromadb
import requests


class VectorStoreService:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.client.get_or_create_collection(name="course_chunks")
        self.ollama_base_url = "http://localhost:11434"
        self.embedding_model = "nomic-embed-text"

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
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

    def add_chunks(self, document_id: str, course_id: str, chunks: list[str]):
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

    def search_chunks(self, course_id: str, query: str, top_k: int = 5):
        query_embedding = self._embed_texts([query])[0]

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"course_id": course_id}
        )

        return results
