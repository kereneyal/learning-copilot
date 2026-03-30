import requests


class CourseSummaryAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def summarize_course(self, summaries: list[str], language: str = "en") -> str:
        if not summaries:
            return "No summaries available for this course."

        combined_summaries = "\n\n".join(summaries[:20])
        prompt = self._build_prompt(combined_summaries, language)

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

    def _build_prompt(self, combined_summaries: str, language: str) -> str:
        if language == "he":
            return f"""
אתה מסכם קורס שלם על בסיס סיכומים של מסמכים שונים.

צור סיכום כללי של הקורס בפורמט הבא:

1. נושא מרכזי של הקורס
2. נושאים עיקריים
3. רעיונות חשובים
4. סיכום קצר של הקורס

סיכומי המסמכים:
{combined_summaries[:15000]}
"""
        else:
            return f"""
You are summarizing an entire course based on multiple document summaries.

Create a structured course summary in the following format:

1. Main course topic
2. Main topics covered
3. Important ideas
4. Short course summary

Document summaries:
{combined_summaries[:15000]}
"""
