import logging
import os
import time
import traceback

import requests
from requests import exceptions as requests_exceptions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider selection
#   1. SUMMARY_PROVIDER env var wins if set explicitly.
#   2. Otherwise: prefer OpenAI when OPENAI_API_KEY is present (faster,
#      bounded latency, truly cancellable via TCP close).
#   3. Fallback: Ollama (local, uncancellable on timeout — see NOTE below).
#
# NOTE on Ollama timeouts: when requests raises Timeout, the TCP connection
# is dropped from the client side, but Ollama's generation goroutine keeps
# running until it finishes.  The HTTP timeout only stops *us* from waiting;
# it does NOT stop Ollama.  This is why summaries should run in a background
# thread and use a short timeout — the document is already "ready" before
# summary starts, so a runaway Ollama job only wastes CPU, not UX.
# ---------------------------------------------------------------------------
_SUMMARY_PROVIDER: str = os.getenv(
    "SUMMARY_PROVIDER",
    "openai" if os.getenv("OPENAI_API_KEY") else "ollama",
)
_SUMMARY_TIMEOUT: int = int(
    os.getenv("SUMMARY_TIMEOUT_S") or os.getenv("OLLAMA_GENERATION_TIMEOUT", "30")
)
_SUMMARY_OLLAMA_MODEL: str = (
    os.getenv("SUMMARY_MODEL") or os.getenv("OLLAMA_GENERATION_MODEL", "qwen2:0.5b")
)
_SUMMARY_OPENAI_MODEL: str = (
    os.getenv("SUMMARY_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
)
_SUMMARY_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")


class SummaryAgent:
    def __init__(
        self,
        model_name: str = None,
        base_url: str = None,
        provider: str = None,
    ):
        self.provider   = provider or _SUMMARY_PROVIDER
        self.base_url   = (base_url or _SUMMARY_BASE_URL).rstrip("/")
        # model_name overrides both Ollama and OpenAI model selection when given
        if model_name:
            self.ollama_model = model_name
            self.openai_model = model_name
        else:
            self.ollama_model = _SUMMARY_OLLAMA_MODEL
            self.openai_model = _SUMMARY_OPENAI_MODEL

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def summarize(self, text: str, language: str = "en") -> str:
        if not text or not text.strip():
            return "No content available for summary."

        prompt   = self._build_prompt(text, language)
        t0       = time.monotonic()

        logger.info(
            "summary_agent.summary_started provider=%s model=%s "
            "timeout_s=%d prompt_chars=%d language=%s",
            self.provider,
            self.openai_model if self.provider == "openai" else self.ollama_model,
            _SUMMARY_TIMEOUT,
            len(prompt),
            language,
        )

        try:
            if self.provider == "openai":
                result = self._generate_openai(prompt)
            else:
                result = self._generate_ollama(prompt)

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "summary_agent.summary_completed provider=%s model=%s "
                "duration_ms=%d result_chars=%d",
                self.provider,
                self.openai_model if self.provider == "openai" else self.ollama_model,
                elapsed_ms,
                len(result),
            )
            return result

        except requests_exceptions.Timeout as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "summary_agent.summary_timeout_client provider=%s model=%s "
                "timeout_s=%d duration_ms=%d error=%s "
                "note='HTTP client timed out — Ollama generation continues on server, "
                "CPU will stay elevated until Ollama finishes internally'",
                self.provider,
                self.ollama_model,
                _SUMMARY_TIMEOUT,
                elapsed_ms,
                exc,
            )
            raise

        except requests_exceptions.ConnectionError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "summary_agent.summary_connection_error provider=%s model=%s "
                "duration_ms=%d error=%s",
                self.provider,
                self.ollama_model,
                elapsed_ms,
                exc,
            )
            raise

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(
                "summary_agent.summary_failed provider=%s model=%s "
                "duration_ms=%d error=%s\n%s",
                self.provider,
                self.openai_model if self.provider == "openai" else self.ollama_model,
                elapsed_ms,
                exc,
                traceback.format_exc(),
            )
            raise

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _generate_ollama(self, prompt: str) -> str:
        endpoint = f"{self.base_url}/api/generate"
        logger.info(
            "summary_agent.provider_used provider=ollama endpoint=%s model=%s",
            endpoint,
            self.ollama_model,
        )
        response = requests.post(
            endpoint,
            json={"model": self.ollama_model, "prompt": prompt, "stream": False},
            timeout=_SUMMARY_TIMEOUT,
        )
        if response.status_code >= 400:
            logger.error(
                "summary_agent.http_error provider=ollama endpoint=%s model=%s "
                "status=%s body=%r",
                endpoint,
                self.ollama_model,
                response.status_code,
                response.text[:400],
            )
        response.raise_for_status()
        return (response.json().get("response") or "").strip()

    def _generate_openai(self, prompt: str) -> str:
        if not _OPENAI_API_KEY:
            raise ValueError(
                "SUMMARY_PROVIDER=openai but OPENAI_API_KEY is not set; "
                "set SUMMARY_PROVIDER=ollama or provide OPENAI_API_KEY"
            )
        from openai import OpenAI
        client = OpenAI(api_key=_OPENAI_API_KEY, timeout=_SUMMARY_TIMEOUT)
        logger.info(
            "summary_agent.provider_used provider=openai model=%s",
            self.openai_model,
        )
        response = client.chat.completions.create(
            model=self.openai_model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError(
                f"Empty response from OpenAI model {self.openai_model}"
            )
        return content.strip()

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

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
