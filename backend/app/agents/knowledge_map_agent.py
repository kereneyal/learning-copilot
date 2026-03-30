import requests


class KnowledgeMapAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def generate_map(self, course_summary: str, document_summaries: list[str], language: str = "en") -> str:
        combined_summaries = "\n\n".join(document_summaries[:20])

        prompt = self._build_prompt(course_summary, combined_summaries, language)

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

    def _build_prompt(self, course_summary: str, document_summaries: str, language: str) -> str:
        if language == "he":
            return f"""
אתה בונה מפת ידע לקורס.

על בסיס סיכום הקורס וסיכומי המסמכים, הפק את המידע הבא:

1. נושאים מרכזיים
2. מושגים חשובים
3. קשרים בין נושאים
4. שאלות אפשריות למבחן

החזר תשובה ברורה ומובנית בעברית.

סיכום הקורס:
{course_summary}

סיכומי מסמכים:
{document_summaries[:12000]}
"""
        else:
            return f"""
You are building a knowledge map for a course.

Based on the course summary and document summaries, generate:

1. Main topics
2. Important concepts
3. Relationships between topics
4. Possible exam questions

Return a clear and structured answer in English.

Course summary:
{course_summary}

Document summaries:
{document_summaries[:12000]}
"""
