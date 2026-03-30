import requests


class QAAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def answer_question(self, question: str, context_chunks: list[str], language: str = "he") -> str:
        context = "\n\n".join(context_chunks[:5])

        prompt = self._build_prompt(question, context, language)

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )

        response.raise_for_status()
        data = response.json()

        return data.get("response", "").strip()

    def _build_prompt(self, question: str, context: str, language: str) -> str:
        if language == "he":
            return f"""
ענה על השאלה על בסיס חומר הקורס בלבד.

אם התשובה לא מופיעה בחומר, אמור זאת בבירור.

חומר רלוונטי:
{context}

שאלה:
{question}

ענה בעברית, בצורה ברורה ומסודרת.
"""
        else:
            return f"""
Answer the question based only on the course material below.

If the answer is not contained in the material, say so clearly.

Relevant course material:
{context}

Question:
{question}

Answer clearly and in English.
"""
