import logging
import os
import time
import traceback

import requests
from requests import exceptions as requests_exceptions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider config — mirrors summary_agent.py pattern.
#
# AGGREGATES_PROVIDER controls both CourseSummaryAgent and KnowledgeMapAgent.
# Auto-mode: prefer OpenAI when OPENAI_API_KEY is set (bounded latency,
# truly cancellable) — otherwise Ollama.
#
# AGGREGATES_TIMEOUT_S: keep short (30s default).  Aggregate generation is
# best-effort; a timeout here never affects document or summary status.
# For Ollama, num_predict caps response token count so generation is bounded
# even if the client timeout fires before Ollama finishes internally.
# ---------------------------------------------------------------------------
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

# Cap input fed to the LLM — keeps prompts sane and prevents Ollama from
# accepting a huge context it then runs for minutes.
_MAX_SUMMARIES = 10         # at most this many document summaries
_MAX_INPUT_CHARS = 8000     # truncate combined input to this length
# Ollama only: cap response token count to bound CPU time.
_OLLAMA_NUM_PREDICT = 500


class CourseSummaryAgent:
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

    def summarize_course(self, summaries: list[str], language: str = "en") -> str:
        if not summaries:
            return "No summaries available for this course."

        capped = summaries[:_MAX_SUMMARIES]
        combined = "\n\n".join(capped)[:_MAX_INPUT_CHARS]
        prompt = self._build_prompt(combined, language)
        t0 = time.monotonic()

        logger.info(
            "course_summary_agent.started provider=%s model=%s timeout_s=%d "
            "input_summaries=%d input_chars=%d",
            self.provider,
            self.openai_model if self.provider == "openai" else self.ollama_model,
            _AGGREGATES_TIMEOUT,
            len(capped),
            len(combined),
        )

        try:
            if self.provider == "openai":
                result = self._generate_openai(prompt)
            else:
                result = self._generate_ollama(prompt)

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "course_summary_agent.completed provider=%s duration_ms=%d result_chars=%d",
                self.provider, elapsed_ms, len(result),
            )
            return result

        except requests_exceptions.Timeout as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "course_summary_agent.timeout provider=%s model=%s "
                "timeout_s=%d duration_ms=%d error=%s "
                "note='client timed out — Ollama may still be generating internally'",
                self.provider, self.ollama_model, _AGGREGATES_TIMEOUT, elapsed_ms, exc,
            )
            raise

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "course_summary_agent.failed provider=%s duration_ms=%d error=%s\n%s",
                self.provider, elapsed_ms, exc, traceback.format_exc(),
            )
            raise

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _generate_ollama(self, prompt: str) -> str:
        endpoint = f"{self.base_url}/api/generate"
        logger.info(
            "course_summary_agent.provider_used provider=ollama endpoint=%s model=%s",
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
                "course_summary_agent.http_error provider=ollama endpoint=%s "
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
            "course_summary_agent.provider_used provider=openai model=%s",
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
{combined_summaries}
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
{combined_summaries}
"""
