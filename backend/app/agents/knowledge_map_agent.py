import logging
import os
import time
import traceback

import requests
from requests import exceptions as requests_exceptions

logger = logging.getLogger(__name__)

# Shares the same provider config block as course_summary_agent.
# See course_summary_agent.py for the reasoning on each constant.
_AGGREGATES_PROVIDER: str = os.getenv(
    "AGGREGATES_PROVIDER",
    "openai" if os.getenv("OPENAI_API_KEY") else "ollama",
)
_AGGREGATES_TIMEOUT: int = int(os.getenv("AGGREGATES_TIMEOUT_S", "30"))
_AGGREGATES_OLLAMA_MODEL: str = (
    os.getenv("AGGREGATES_MODEL") or os.getenv("OLLAMA_GENERATION_MODEL", "qwen2:0.5b")
)
_AGGREGATES_OPENAI_MODEL: str = (
    os.getenv("AGGREGATES_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
)
_AGGREGATES_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

_MAX_SUMMARIES = 10
_MAX_SUMMARIES_CHARS = 6000   # tighter than course summary — knowledge map builds on top
_MAX_COURSE_SUMMARY_CHARS = 2000
_OLLAMA_NUM_PREDICT = 600     # slightly more headroom for structured map output


class KnowledgeMapAgent:
    def __init__(
        self,
        model_name: str = None,
        base_url: str = None,
        provider: str = None,
    ):
        self.provider   = provider or _AGGREGATES_PROVIDER
        self.base_url   = (base_url or _AGGREGATES_BASE_URL).rstrip("/")
        if model_name:
            self.ollama_model = model_name
            self.openai_model = model_name
        else:
            self.ollama_model = _AGGREGATES_OLLAMA_MODEL
            self.openai_model = _AGGREGATES_OPENAI_MODEL

    def generate_map(
        self,
        course_summary: str,
        document_summaries: list[str],
        language: str = "en",
    ) -> str:
        capped = document_summaries[:_MAX_SUMMARIES]
        combined = "\n\n".join(capped)[:_MAX_SUMMARIES_CHARS]
        cs = (course_summary or "")[:_MAX_COURSE_SUMMARY_CHARS]
        prompt = self._build_prompt(cs, combined, language)
        t0 = time.monotonic()

        logger.info(
            "knowledge_map_agent.started provider=%s model=%s timeout_s=%d "
            "input_summaries=%d input_chars=%d course_summary_chars=%d",
            self.provider,
            self.openai_model if self.provider == "openai" else self.ollama_model,
            _AGGREGATES_TIMEOUT,
            len(capped),
            len(combined),
            len(cs),
        )

        try:
            if self.provider == "openai":
                result = self._generate_openai(prompt)
            else:
                result = self._generate_ollama(prompt)

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "knowledge_map_agent.completed provider=%s duration_ms=%d result_chars=%d",
                self.provider, elapsed_ms, len(result),
            )
            return result

        except requests_exceptions.Timeout as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "knowledge_map_agent.timeout provider=%s model=%s "
                "timeout_s=%d duration_ms=%d error=%s "
                "note='client timed out — Ollama may still be generating internally'",
                self.provider, self.ollama_model, _AGGREGATES_TIMEOUT, elapsed_ms, exc,
            )
            raise

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "knowledge_map_agent.failed provider=%s duration_ms=%d error=%s\n%s",
                self.provider, elapsed_ms, exc, traceback.format_exc(),
            )
            raise

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _generate_ollama(self, prompt: str) -> str:
        endpoint = f"{self.base_url}/api/generate"
        logger.info(
            "knowledge_map_agent.provider_used provider=ollama endpoint=%s model=%s",
            endpoint, self.ollama_model,
        )
        response = requests.post(
            endpoint,
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": _OLLAMA_NUM_PREDICT},
            },
            timeout=_AGGREGATES_TIMEOUT,
        )
        if response.status_code >= 400:
            logger.error(
                "knowledge_map_agent.http_error provider=ollama endpoint=%s "
                "model=%s status=%s body=%r",
                endpoint, self.ollama_model,
                response.status_code, response.text[:400],
            )
        response.raise_for_status()
        return (response.json().get("response") or "").strip()

    def _generate_openai(self, prompt: str) -> str:
        if not _OPENAI_API_KEY:
            raise ValueError(
                "AGGREGATES_PROVIDER=openai but OPENAI_API_KEY is not set"
            )
        from openai import OpenAI
        client = OpenAI(api_key=_OPENAI_API_KEY, timeout=_AGGREGATES_TIMEOUT)
        logger.info(
            "knowledge_map_agent.provider_used provider=openai model=%s",
            self.openai_model,
        )
        response = client.chat.completions.create(
            model=self.openai_model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError(f"Empty response from OpenAI model {self.openai_model}")
        return content.strip()

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self, course_summary: str, document_summaries: str, language: str
    ) -> str:
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
{document_summaries}
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
{document_summaries}
"""
