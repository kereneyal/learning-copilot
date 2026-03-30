import requests


class RouterAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def detect_intent(self, question: str) -> str:
        prompt = f"""
You are a routing agent.

Classify the user's request into exactly one of these intents:
- qa
- course_summary
- knowledge_map
- exam

Rules:
- Return only one word
- No explanation
- No punctuation

Examples:
User: What is fiduciary duty?
Intent: qa

User: Summarize the whole course
Intent: course_summary

User: What are the main topics and concepts in this course?
Intent: knowledge_map

User: generate exam questions
Intent: exam

User request:
{question}
"""

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )

        response.raise_for_status()
        data = response.json()
        intent = data.get("response", "").strip().lower()

        if intent not in {"qa", "course_summary", "knowledge_map","exam"}:
            return "qa"

        return intent
