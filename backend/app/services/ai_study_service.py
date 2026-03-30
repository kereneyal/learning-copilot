import json
import os
import re
from typing import Dict, List

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


def _clean_text(text: str) -> str:
    text = text or ""
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sentences(text: str) -> List[str]:
    raw = re.split(r"[.\n]+", text)
    return [s.strip() for s in raw if s and s.strip()]


def _local_summary(text: str) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return "לא נמצא מספיק תוכן כדי לייצר סיכום."
    return "\n".join(f"- {s}" for s in sentences[:8])


def _local_flashcards(text: str) -> List[Dict[str, str]]:
    sentences = _split_sentences(text)[:5]
    if not sentences:
        return [{"question": "מה הופיע במסמך?", "answer": "לא נמצא מספיק תוכן."}]
    return [
        {
            "question": f"מה הנקודה המרכזית בקטע {i+1}?",
            "answer": s,
        }
        for i, s in enumerate(sentences)
    ]


def _local_quiz(text: str) -> List[Dict[str, str]]:
    sentences = _split_sentences(text)[:5]
    if not sentences:
        return [{"question": "מה המסמך מנסה להסביר?", "answer": "לא נמצא מספיק תוכן."}]
    return [
        {
            "question": f"הסבר בקצרה: {s[:120]}",
            "answer": s,
        }
        for s in sentences
    ]


def _fallback_response(text: str) -> Dict:
    return {
        "summary": _local_summary(text),
        "flashcards": _local_flashcards(text),
        "quiz": _local_quiz(text),
        "provider": "local_fallback",
    }


class AIStudyService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None

        if self.api_key and OpenAI is not None:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception:
                self.client = None

    def generate(self, text: str, mode: str = "summary") -> Dict:
        text = _clean_text(text)

        if not text:
            return {
                "summary": "לא סופק טקסט.",
                "flashcards": [],
                "quiz": [],
                "provider": "empty_input",
            }

        if self.client is None:
            return _fallback_response(text)

        prompt = f"""
You are an educational study assistant.

Given the source text below, return strict JSON with this exact structure:
{{
  "summary": "string",
  "flashcards": [
    {{"question": "string", "answer": "string"}}
  ],
  "quiz": [
    {{"question": "string", "answer": "string"}}
  ]
}}

Requirements:
- Summary should be concise but useful for study.
- Flashcards should contain 5 high-value study cards.
- Quiz should contain 5 study questions with short answers.
- Use the same language as the source text when possible.
- Return JSON only, no markdown, no explanation.

SOURCE TEXT:
{text[:12000]}
""".strip()

        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": "You produce strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )

            if not getattr(response, "choices", None):
                raise ValueError("No choices returned from model")

            first_choice = response.choices[0]
            message = getattr(first_choice, "message", None)
            content = getattr(message, "content", None) or "{}"

            data = json.loads(content)

            return {
                "summary": data.get("summary", ""),
                "flashcards": data.get("flashcards", []),
                "quiz": data.get("quiz", []),
                "provider": "openai",
            }

        except Exception:
            return _fallback_response(text)
