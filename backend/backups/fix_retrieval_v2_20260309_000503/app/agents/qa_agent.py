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
