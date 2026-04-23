import logging
import os
import re
import traceback

import requests
from requests import exceptions as requests_exceptions
from sqlalchemy.orm import Session

from app.services.vector_store import VectorStoreService
from app.services.source_enricher import enrich_sources
from app.services.hybrid_qa_retrieval import ABSTAIN_MESSAGE_HE, hybrid_retrieve_for_qa
from app.services.mc_context_helper import order_chunks_for_mc
from app.services.mc_response_normalizer import (
    normalize_mc_model_output,
    refine_mc_explanation_grounding,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context limits — keeps prompts short enough for CPU-only LLMs.
# Override via env vars without code changes.
# ---------------------------------------------------------------------------
# Max chunks forwarded to the LLM (retrieval may return more; extras are dropped).
_QA_MAX_CONTEXT_CHUNKS: int = int(os.getenv("QA_MAX_CONTEXT_CHUNKS", "3"))
# Each chunk is truncated to this many characters before being placed in the prompt.
# Total context budget = QA_MAX_CONTEXT_CHUNKS × QA_MAX_CHUNK_CHARS ≈ 1200 chars / ~300 tokens.
_QA_MAX_CHUNK_CHARS: int = int(os.getenv("QA_MAX_CHUNK_CHARS", "400"))
# Generation timeout in seconds.
# Expected latency on a 16 GB CPU-only machine (warm, ~1500-char prompt):
#   qwen2:0.5b   →  5–15 s  → OLLAMA_GENERATION_TIMEOUT=45   (0.5B — fastest)
#   llama3.2:1b  → 20–40 s  → OLLAMA_GENERATION_TIMEOUT=90   (1.2B)
#   phi3:mini    → 90–180 s → OLLAMA_GENERATION_TIMEOUT=240  (3.8B — NOT lightweight)
#   llama3:latest→ 120–300 s→ OLLAMA_GENERATION_TIMEOUT=300  (8B)
_GENERATION_TIMEOUT: int = int(os.getenv("OLLAMA_GENERATION_TIMEOUT", "45"))

# For definition questions the top chunk gets extra room so acronym breakdowns
# (which typically span ~500-600 chars) are never truncated mid-entry.
_QA_DEFINITION_CHUNK_CHARS: int = int(os.getenv("QA_DEFINITION_CHUNK_CHARS", "600"))

# ---------------------------------------------------------------------------
# Provider routing — definition/acronym questions can be routed to OpenAI for
# higher-quality answers; everything else stays on local Ollama.
# ---------------------------------------------------------------------------
# Default provider for all questions: "ollama" | "openai"
_QA_PROVIDER_DEFAULT: str = os.getenv("QA_PROVIDER_DEFAULT", "ollama")
# Provider for definition/acronym questions: "ollama" | "openai"
_QA_PROVIDER_DEFINITION: str = os.getenv("QA_PROVIDER_DEFINITION", "openai")
_OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
_OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
_OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "30"))

_DEFINITION_RE = re.compile(
    r"^("
    r"מה\s+זה\s+"                   # מה זה
    r"|מה\s+ה-"                     # מה ה- (hyphen directly before term, no space needed)
    r"|מה\s+(הוא|היא)\s+"           # מה הוא / מה היא
    r"|הגדר\s+את\s+"                # הגדר את
    r"|מה\s+המשמעות\s+"             # מה המשמעות של
    r"|מה\s+פירוש\s+"               # מה פירוש
    r"|what\s+is\b"                  # What is
    r"|define\b"                     # Define
    r"|explain\s+the\s+term\b"       # Explain the term
    r")",
    re.IGNORECASE,
)

_ACRONYM_RE = re.compile(
    r"^("
    r"מה\s+פירוש\s+ראשי\s+התיבות\b"        # מה פירוש ראשי התיבות X
    r"|מה\s+ראשי\s+התיבות\b"               # מה ראשי התיבות של X
    r"|what\s+does\s+\S+\s+stand\s+for\b"  # What does X stand for?
    r"|what\s+is\s+the\s+(?:full\s+)?acronym\b"  # What is the (full) acronym for
    r")",
    re.IGNORECASE,
)


def _is_definition_question(question: str) -> bool:
    return bool(_DEFINITION_RE.match(question.strip()))


def _is_acronym_question(question: str) -> bool:
    return bool(_ACRONYM_RE.match(question.strip()))


def _limit_to_two_sentences(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return stripped
    parts = re.split(r"(?<=[.!?])\s+", stripped)
    if len(parts) <= 2:
        return stripped
    return " ".join(parts[:2]).strip()


def _generate_with_openai(prompt: str, api_key: str, model: str, timeout: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=timeout)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError(f"Empty response from OpenAI model {model}")
    return content


def _generate_with_ollama(
    prompt: str, base_url: str, model_name: str, timeout: int
) -> str:
    endpoint = f"{base_url}/api/generate"
    response = requests.post(
        endpoint,
        json={"model": model_name, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    if response.status_code >= 400:
        logger.error(
            "qa.llm_http_error endpoint=%s model=%s status=%s body=%r",
            endpoint,
            model_name,
            response.status_code,
            response.text[:400],
        )
    response.raise_for_status()
    payload = response.json()
    answer = payload.get("response")
    if not answer:
        raise ValueError(f"Missing 'response' key in Ollama reply: {payload}")
    return answer


class QAAgent:
    def __init__(
        self,
        model_name: str = None,
        base_url: str = None,
    ):
        self.vector_store = VectorStoreService()
        # Read from env so the model name can be overridden without code changes.
        # Default changed from "llama3.1" (wrong) to "llama3:latest" (matches
        # what Ollama actually tags the model as on pull).
        self.model_name = (
            model_name
            or os.getenv("OLLAMA_GENERATION_MODEL", "qwen2:0.5b")
        )
        self.base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        )
        logger.info(
            "qa_agent.init model=%s base_url=%s max_chunks=%d max_chunk_chars=%d timeout=%ds",
            self.model_name,
            self.base_url,
            _QA_MAX_CONTEXT_CHUNKS,
            _QA_MAX_CHUNK_CHARS,
            _GENERATION_TIMEOUT,
        )

    def validate_generation_health(self, timeout_s: int = 15) -> bool:
        """
        Smoke-test the generation endpoint with a one-token prompt.
        Logs a clear error (including the pull command) if the model is missing.
        """
        endpoint = f"{self.base_url}/api/generate"
        try:
            resp = requests.post(
                endpoint,
                json={"model": self.model_name, "prompt": "hi", "stream": False},
                timeout=timeout_s,
            )
            if resp.status_code == 404:
                logger.error(
                    "qa_agent.generation_health_missing model=%s — "
                    "run: ollama pull %s",
                    self.model_name,
                    self.model_name,
                )
                return False
            resp.raise_for_status()
            logger.info(
                "qa_agent.generation_health_ok model=%s endpoint=%s",
                self.model_name,
                endpoint,
            )
            return True
        except Exception as exc:
            logger.error(
                "qa_agent.generation_health_failed model=%s endpoint=%s error=%s",
                self.model_name,
                endpoint,
                exc,
            )
            return False

    def answer(
        self,
        question,
        db: Session,
        course_id=None,
        lecture_id=None,
        qa_mode: str = "open",
        mc_parsed=None,
    ):
        mc_opts = (mc_parsed.get("options") or []) if mc_parsed else []
        mc_ok = qa_mode == "multiple_choice" and mc_parsed and len(mc_opts) >= 2

        # FIX: use the stem only for MC retrieval — blending all option texts
        # into the query dilutes the embedding and pulls in chunks about
        # distractors (wrong options), degrading answer quality.
        if mc_ok:
            stem = (mc_parsed.get("stem") or "").strip()
            # Fall back to the full retrieval_query only if the stem is too short
            # to produce meaningful results on its own.
            retrieval_question = stem if len(stem) >= 15 else (
                mc_parsed.get("retrieval_query") or question
            )
        else:
            retrieval_question = question

        chunks, should_abstain, abstain_reason = hybrid_retrieve_for_qa(
            self.vector_store,
            question=retrieval_question,
            course_id=course_id,
            lecture_id=lecture_id,
        )

        logger.info(
            "qa.retrieval course_id=%s lecture_id=%s qa_mode=%s "
            "retrieval_q_len=%d chunks=%d abstain=%s reason=%s",
            course_id,
            lecture_id,
            qa_mode,
            len(retrieval_question),
            len(chunks),
            should_abstain,
            abstain_reason,
        )

        # --- open QA with no context → abstain immediately ---
        if not mc_ok and (should_abstain or not chunks):
            return {
                "answer": ABSTAIN_MESSAGE_HE if should_abstain else "לא נמצא מידע רלוונטי במסמכים.",
                "sources": [],
            }

        # FIX: MC with no relevant context → return UNKNOWN without calling
        # the LLM.  Previously the model was asked to "reason from stem and
        # options only", which produced confident hallucinations for factual
        # questions (exact percentages, dates, legal thresholds, etc.).
        if mc_ok and (should_abstain or not chunks):
            logger.info(
                "qa.mc_no_context_early_return course_id=%s — returning UNKNOWN without LLM call",
                course_id,
            )
            return {
                "answer": ABSTAIN_MESSAGE_HE,
                "sources": [],
                "multiple_choice": {
                    "correct_letter": "UNKNOWN",
                    "explanation": ABSTAIN_MESSAGE_HE,
                },
            }

        if mc_ok:
            chunks = order_chunks_for_mc(chunks, mc_parsed)

        # Limit chunks forwarded to the LLM to keep prompt size manageable on CPU.
        if len(chunks) > _QA_MAX_CONTEXT_CHUNKS:
            logger.info(
                "qa.context_truncated total=%d kept=%d",
                len(chunks),
                _QA_MAX_CONTEXT_CHUNKS,
            )
            chunks = chunks[:_QA_MAX_CONTEXT_CHUNKS]

        # Truncate individual chunks so a single long chunk can't bloat the prompt.
        # For definition questions the top chunk gets extra headroom so that
        # acronym breakdowns (e.g. V-U-C-A each on its own line) are never cut mid-entry.
        is_def_q = _is_definition_question(question) or _is_acronym_question(question)
        context_parts = []
        for i, c in enumerate(chunks):
            text = c.get("text") or ""
            limit = _QA_DEFINITION_CHUNK_CHARS if (is_def_q and i == 0) else _QA_MAX_CHUNK_CHARS
            if len(text) > limit:
                text = text[:limit] + "…"
            context_parts.append(text)
        context = "\n\n".join(context_parts) if context_parts else ""

        # Log each context chunk for post-mortem debugging (DEBUG level to
        # avoid noise in production).
        for i, c in enumerate(chunks):
            logger.debug(
                "qa.context_chunk rank=%d doc=%s idx=%s snippet=%r",
                i,
                c.get("document_id"),
                c.get("chunk_index"),
                (c.get("text") or "")[:80],
            )

        if qa_mode == "multiple_choice" and mc_parsed:
            stem = (mc_parsed.get("stem") or "").strip()
            opts = mc_parsed.get("options") or []
            opts_block = "\n".join(f"{o['letter']}. {o['text']}" for o in opts)
            stem_display = stem if stem else "שאלת הבחירה המרובה שלהלן"
            mc_discipline = (
                "Pick the best option using ONLY the Context. Rules:\n"
                "- CORRECT and EXPLANATION must match — if CORRECT is A, explain A only.\n"
                "- Never cite a number, date, or percentage unless it appears verbatim in Context.\n"
                "- Output CORRECT: UNKNOWN if Context is insufficient or conflicting.\n"
                "- Match the question language (Hebrew question → Hebrew explanation).\n"
                f"- If CORRECT is UNKNOWN, EXPLANATION must be exactly: {ABSTAIN_MESSAGE_HE}"
            )

            ctx_rules = (
                "Course excerpts are below. Prefer evidence that directly supports the chosen option.\n"
                + mc_discipline
            )
            prompt = f"""
You are answering a multiple-choice question.

Instructions:
{ctx_rules}

Reply in exactly this format (two lines, then blank line, then explanation):
CORRECT: <one letter only, or UNKNOWN>
EXPLANATION:
<your explanation>

Context:
{context}

Question:
{stem_display}

Options:
{opts_block}
"""
        elif is_def_q:
            prompt = f"""You are a precise, source-grounded study assistant.

Rules for definition questions:
1. Answer in at most 2 sentences.
2. Start immediately with the direct definition in sentence 1. Do not add any intro such as "According to the context" or broad background before the definition.
3. If the Context contains an acronym expansion, include it explicitly in sentence 1 and list every component that appears in the Context. Do not skip any component.
4. Prefer the exact source-grounded wording from the Context. Do NOT use your own knowledge or vague paraphrases.
5. Reply in the same language as the question (Hebrew question → Hebrew answer; English question → English answer).
6. If the Context contains no definition, reply exactly: "לא מצאתי מידע מספיק במסמכי הקורס כדי לענות בוודאות."

Example (Hebrew):
Question: "מה זה VUCA?"
Answer: "VUCA הוא ראשי תיבות של Volatility (תנודתיות), Uncertainty (אי-ודאות), Complexity (מורכבות), Ambiguity (עמימות)."

Example (English):
Question: "What does VUCA stand for?"
Answer: "VUCA stands for Volatility, Uncertainty, Complexity, and Ambiguity."

Context:
{context}

Question:
{question}
"""
        else:
            prompt = f"""אתה עוזר לימודי מדויק ומבוסס-מקורות.

כללי מענה:
1. ענה רק לפי ה-Context.
2. אם אין מידע מספיק, ענה: "לא מצאתי מידע מספיק במסמכי הקורס כדי לענות בוודאות."
3. תשובה קצרה ומדויקת על פני כללית.
4. אל תשתמש בניסוחים עמומים ("המושג מתאר", "ניתן לומר ש", "בהקשר רחב") אלא אם הם באים ישירות מהמקור.
5. אל תכניס ידע חיצוני שלא מופיע ב-Context.

ענה בעברית אלא אם השאלה נשאלה בשפה אחרת.

Context:
{context}

שאלה:
{question}
"""

        # ------------------------------------------------------------------
        # Provider routing
        # ------------------------------------------------------------------
        use_openai_for_this = (
            _is_definition_question(question) or _is_acronym_question(question)
        ) and _QA_PROVIDER_DEFINITION == "openai"

        selected_provider = "openai" if use_openai_for_this else _QA_PROVIDER_DEFAULT
        selected_model = _OPENAI_MODEL if selected_provider == "openai" else self.model_name
        routing_reason = "definition_or_acronym" if use_openai_for_this else "default"

        logger.info(
            "qa.provider.selected provider=%s reason=%s model=%s prompt_chars=%d context_chunks=%d",
            selected_provider,
            routing_reason,
            selected_model,
            len(prompt),
            len(chunks),
        )

        answer: str | None = None

        # Try OpenAI when selected and an API key is configured.
        if selected_provider == "openai" and _OPENAI_API_KEY:
            try:
                answer = _generate_with_openai(prompt, _OPENAI_API_KEY, _OPENAI_MODEL, _OPENAI_TIMEOUT)
                logger.debug(
                    "qa.llm_response provider=openai model=%s answer_chars=%d preview=%r",
                    _OPENAI_MODEL,
                    len(answer),
                    answer[:120].replace("\n", " "),
                )
            except Exception as exc:
                logger.error(
                    "qa.provider.fallback triggered=True provider=openai model=%s error=%s "
                    "— falling back to ollama model=%s",
                    _OPENAI_MODEL,
                    exc,
                    self.model_name,
                )
                answer = None

        # Ollama: either as the default provider or as a fallback.
        if answer is None:
            ollama_endpoint = f"{self.base_url}/api/generate"
            try:
                answer = _generate_with_ollama(
                    prompt, self.base_url, self.model_name, _GENERATION_TIMEOUT
                )
                logger.debug(
                    "qa.llm_response provider=ollama model=%s answer_chars=%d preview=%r",
                    self.model_name,
                    len(answer),
                    answer[:120].replace("\n", " "),
                )
            except requests_exceptions.Timeout as exc:
                _lighter = {
                    "llama3:latest": "llama3.2:1b or qwen2:0.5b",
                    "llama3.2:1b": "qwen2:0.5b",
                    "phi3:mini": "llama3.2:1b or qwen2:0.5b",
                }.get(self.model_name, "qwen2:0.5b")
                logger.error(
                    "qa.llm_timeout endpoint=%s model=%s timeout=%ds prompt_chars=%d error=%s "
                    "— switch to a faster model (%s) or raise OLLAMA_GENERATION_TIMEOUT",
                    ollama_endpoint,
                    self.model_name,
                    _GENERATION_TIMEOUT,
                    len(prompt),
                    exc,
                    _lighter,
                )
                return {
                    "answer": "המענה לקח יותר מדי זמן. נסה שאלה קצרה יותר או פנה למנהל המערכת.",
                    "sources": [],
                }
            except requests_exceptions.ConnectionError as exc:
                logger.error(
                    "qa.llm_unavailable endpoint=%s model=%s error=%s",
                    ollama_endpoint,
                    self.model_name,
                    exc,
                )
                return {
                    "answer": "שירות המענה אינו זמין כרגע. נסה שוב בעוד רגע.",
                    "sources": [],
                }
            except Exception as exc:
                logger.error(
                    "qa.llm_error endpoint=%s model=%s error=%s\n%s",
                    ollama_endpoint,
                    self.model_name,
                    exc,
                    traceback.format_exc(),
                )
                return {
                    "answer": "אירעה שגיאה בזמן יצירת התשובה.",
                    "sources": [],
                }

        if is_def_q:
            answer = _limit_to_two_sentences(answer)

        raw_sources = []
        for c in chunks:
            raw_sources.append({
                "course_id": c.get("course_id"),
                "lecture_id": c.get("lecture_id"),
                "document_id": c.get("document_id"),
                "snippet": c.get("snippet"),
                "chunk_index": c.get("chunk_index"),
            })

        sources = enrich_sources(db, raw_sources)

        if qa_mode == "multiple_choice" and mc_parsed:
            norm = normalize_mc_model_output(answer, mc_parsed)
            letter = norm.get("correct_letter") or "UNKNOWN"
            explanation = norm.get("explanation") or ""
            refined = refine_mc_explanation_grounding(
                letter, explanation, mc_parsed, context
            )
            letter = refined["correct_letter"]
            explanation = refined["explanation"]

            logger.info(
                "qa.mc_result letter=%s grounding_replaced=%s",
                letter,
                explanation == refined.get("explanation") and explanation != norm.get("explanation"),
            )

            return {
                "answer": explanation,
                "sources": sources,
                "multiple_choice": {
                    "correct_letter": letter,
                    "explanation": explanation,
                },
            }

        return {
            "answer": answer,
            "sources": sources,
        }
