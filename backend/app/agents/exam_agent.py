import requests
import json


class ExamAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def generate_exam(self, course_summary: str, language: str = "en") -> str:
        prompt = self._build_prompt(course_summary, language)

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

    def _build_prompt(self, course_summary: str, language: str) -> str:
        if language == "he":
            return f"""
על בסיס סיכום הקורס הבא צור מבחן בפורמט JSON תקין בלבד.

מבנה ה-JSON חייב להיות בדיוק כך:
{{
  "multiple_choice": [
    {{
      "question": "שאלה",
      "options": ["א", "ב", "ג", "ד"],
      "answer": "א"
    }}
  ],
  "open_questions": [
    {{
      "question": "שאלה פתוחה",
      "answer_guidance": "קו מנחה לתשובה"
    }}
  ],
  "advanced_questions": [
    {{
      "question": "שאלת חשיבה",
      "answer_guidance": "קו מנחה לתשובה"
    }}
  ]
}}

דרישות:
- 5 שאלות אמריקאיות
- 3 שאלות פתוחות
- 2 שאלות מתקדמות
- החזר JSON בלבד, בלי הסברים, בלי markdown

סיכום הקורס:
{course_summary}
"""
        else:
            return f"""
Based on the following course summary, generate an exam in valid JSON only.

The JSON must match exactly this structure:
{{
  "multiple_choice": [
    {{
      "question": "Question text",
      "options": ["A", "B", "C", "D"],
      "answer": "A"
    }}
  ],
  "open_questions": [
    {{
      "question": "Open question",
      "answer_guidance": "What a good answer should include"
    }}
  ],
  "advanced_questions": [
    {{
      "question": "Advanced thinking question",
      "answer_guidance": "What a good answer should include"
    }}
  ]
}}

Requirements:
- 5 multiple choice questions
- 3 open questions
- 2 advanced questions
- Return JSON only, no markdown, no explanations

Course summary:
{course_summary}
"""
