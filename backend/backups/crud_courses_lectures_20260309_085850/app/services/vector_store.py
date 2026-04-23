import chromadb
import requests


class VectorStoreService:

    def __init__(self):
        self.client = chromadb.PersistentClient(path="./chroma_db")

        self.collection = self.client.get_or_create_collection(
            name="course_chunks"
        )

        self.ollama_base_url = "http://localhost:11434"
        self.embedding_model = "nomic-embed-text"


    def _embed(self, text):

        response = requests.post(
            f"{self.ollama_base_url}/api/embed",
            json={
                "model": self.embedding_model,
                "input": text
            }
        )

        response.raise_for_status()

        return response.json()["embeddings"][0]


    def add_chunks(self, document_id, course_id, lecture_id, chunks):

        embeddings = [self._embed(chunk) for chunk in chunks]

        ids = [f"{document_id}_{i}" for i in range(len(chunks))]

        metadatas = []

        for i in range(len(chunks)):

            metadatas.append({
                "document_id": document_id,
                "course_id": course_id,
                "lecture_id": lecture_id,
                "chunk_index": i
            })

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas
        )


    def search(self, query, course_id=None, lecture_id=None, top_k=12):

        embedding = self._embed(query)

        where = {}

        if course_id:
            where["course_id"] = course_id

        if lecture_id:
            where["lecture_id"] = lecture_id

        if where:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                where=where
            )
        else:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=top_k
            )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        chunks = []

        for doc, meta in zip(documents, metadatas):

            chunks.append({
                "text": doc,
                "snippet": doc[:300],
                "course_id": meta.get("course_id"),
                "lecture_id": meta.get("lecture_id"),
                "document_id": meta.get("document_id")
            })

        return chunks
