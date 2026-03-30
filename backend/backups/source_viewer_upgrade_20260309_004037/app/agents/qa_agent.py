import requests
from app.services.vector_store import VectorStoreService


class QAAgent:

    def __init__(self):

        self.vector_store = VectorStoreService()

        self.ollama_url = "http://localhost:11434/api/generate"

        self.model = "llama3.1"


    def answer(self, question, course_id=None, lecture_id=None):

        chunks = self.vector_store.search(
            query=question,
            course_id=course_id,
            lecture_id=lecture_id
        )

        if not chunks:

            return {
                "answer": "לא נמצא מידע רלוונטי במסמכים.",
                "sources": []
            }

        context = "\n\n".join([c["text"] for c in chunks[:6]])

        prompt = f"""
Answer the question using ONLY the course material.

If the question is in Hebrew answer in Hebrew.
If the question is in English answer in English.

Context:
{context}

Question:
{question}
"""

        response = requests.post(
            self.ollama_url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        answer = response.json()["response"]

        sources = []

        for c in chunks[:3]:

            sources.append({
                "course_id": c["course_id"],
                "lecture_id": c["lecture_id"],
                "document_id": c["document_id"],
                "snippet": c["snippet"]
            })

        return {
            "answer": answer,
            "sources": sources
        }
