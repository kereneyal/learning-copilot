import requests
from app.services.vector_store import VectorStoreService


class QAAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.vector_store = VectorStoreService()

    def retrieve_chunks(self, course_id: str, question: str, top_k: int = 12):
        chunks = self.vector_store.search_chunks(course_id, question, top_k=top_k)

        if not chunks:
            chunks = self.vector_store.keyword_search(course_id, question, top_k=5)

        return chunks

    def answer_question(self, question: str, context_chunks, language: str = "en") -> str:
        context = "\n\n".join([c["text"] if isinstance(c, dict) else c for c in context_chunks[:6]])
        prompt = self._build_prompt(question, context, language)

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            },
            timeout=180
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def _build_prompt(self, question: str, context: str, language: str) -> str:
        if language == "he":
            return f"""
ענה על השאלה על בסיס חומר הקורס בלבד.

אם המידע קיים חלקית, ענה לפי מה שקיים והבהר מה לא ודאי.
אם אין מידע בכלל, אמור זאת בבירור.

חומר רלוונטי:
{context}

שאלה:
{question}

ענה בעברית, בצורה ברורה ומסודרת.
"""
        else:
            return f"""
Answer the question based only on the course material below.

If the information is partial, answer based on the available material and clearly note uncertainty.
If the answer is not in the material at all, say so clearly.

Relevant course material:
{context}

Question:
{question}

Answer clearly and in English.
"""


def answer_question(course_id: str, question: str, language: str = "en"):
    agent = QAAgent()
    chunks = agent.retrieve_chunks(course_id, question, top_k=12)

    if not chunks:
        fallback = "לא נמצא מידע רלוונטי במסמכים." if language == "he" else "No relevant information was found in the course materials."
        return {
            "answer": fallback,
            "sources": []
        }

    answer = agent.answer_question(question, chunks, language)

    sources = [
        {
            "document_id": c.get("document_id"),
            "lecture_id": c.get("lecture_id"),
            "chunk_index": c.get("chunk_index"),
            "snippet": c.get("snippet")
        }
        for c in chunks[:3]
    ]

    return {
        "answer": answer,
        "sources": sources
    }
