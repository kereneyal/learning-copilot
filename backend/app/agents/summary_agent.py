import requests


class SummaryAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def summarize(self, text: str, language: str = "en") -> str:
        if not text or not text.strip():
            return "No content available for summary."

        prompt = self._build_prompt(text, language)

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

    def _build_prompt(self, text: str, language: str) -> str:
        if language == "he":
            return f"""
אתה מסכם חומר לימודי.

סכם את הטקסט הבא בצורה ברורה ומסודרת.

החזר בפורמט הבא:
1. נושא מרכזי
2. נקודות עיקריות
3. מושגים חשובים
4. סיכום קצר

טקסט:
{text[:12000]}
"""
        else:
            return f"""
You are summarizing study material.

Summarize the following text clearly and in a structured way.

Return in this format:
1. Main topic
2. Key points
3. Important concepts
4. Short summary

Text:
{text[:12000]}
"""
