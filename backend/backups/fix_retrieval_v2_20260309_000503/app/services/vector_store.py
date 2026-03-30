import chromadb
from sentence_transformers import SentenceTransformer


class VectorStoreService:

    def __init__(self):

        self.client = chromadb.PersistentClient(path="./chroma_db")

        self.collection = self.client.get_or_create_collection(
            name="course_chunks"
        )

        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


    def add_chunks(self, document_id: str, course_id: str, lecture_id: str, chunks):

        if not chunks:
            return

        embeddings = self.embedding_model.encode(chunks).tolist()

        ids = [f"{document_id}_{i}" for i in range(len(chunks))]

        metadatas = [
            {
                "document_id": document_id,
                "course_id": course_id,
                "lecture_id": lecture_id,
                "chunk_index": i
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

        query_embedding = self.embedding_model.encode([query]).tolist()[0]

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"course_id": course_id}
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        chunks = []

        for doc, meta in zip(documents, metadatas):

            snippet = doc[:300]

            chunks.append({
                "text": doc,
                "snippet": snippet,
                "document_id": meta.get("document_id"),
                "lecture_id": meta.get("lecture_id"),
                "chunk_index": meta.get("chunk_index")
            })

        return chunks
