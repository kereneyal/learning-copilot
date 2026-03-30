#!/bin/bash

set -e

STAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/retrieval_upgrade_$STAMP"

mkdir -p "$BACKUP_DIR"

backup_file() {
  if [ -f "$1" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$1")"
    cp "$1" "$BACKUP_DIR/$1"
    echo "Backed up $1"
  fi
}

echo "Backing up files..."

backup_file app/services/vector_store.py
backup_file app/agents/qa_agent.py
backup_file app/routes/copilot.py

echo "Upgrading vector_store..."

cat > app/services/vector_store.py <<'EOF'
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
EOF


echo "Creating QA agent..."

cat > app/agents/qa_agent.py <<'EOF'
from app.services.vector_store import VectorStoreService
import ollama


vector_store = VectorStoreService()


def answer_question(course_id: str, question: str):

    chunks = vector_store.search_chunks(course_id, question, top_k=12)

    if not chunks:

        return {
            "answer": "לא נמצא מידע רלוונטי במסמכים.",
            "sources": []
        }

    context = "\n\n".join([c["text"] for c in chunks[:6]])

    prompt = f"""
You are an academic assistant.

Use the context below to answer the question.

If the question is Hebrew, answer in Hebrew.
If English, answer in English.

Context:
{context}

Question:
{question}
"""

    response = ollama.chat(
        model="llama3",
        messages=[{"role": "user", "content": prompt}]
    )

    answer = response["message"]["content"]

    sources = [
        {
            "document_id": c["document_id"],
            "lecture_id": c["lecture_id"],
            "chunk_index": c["chunk_index"],
            "snippet": c["snippet"]
        }
        for c in chunks[:3]
    ]

    return {
        "answer": answer,
        "sources": sources
    }
EOF


echo "Upgrading copilot route..."

cat > app/routes/copilot.py <<'EOF'
from fastapi import APIRouter
from pydantic import BaseModel
from app.agents.qa_agent import answer_question


router = APIRouter()


class QuestionRequest(BaseModel):

    course_id: str
    question: str


@router.post("/copilot/ask")

def ask(req: QuestionRequest):

    result = answer_question(req.course_id, req.question)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "intent": "qa"
    }
EOF


echo "Retrieval v2 installed successfully."
echo "Restart backend to activate."
