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


class QAAgent:
    def __init__(self, model_name: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.vector_store = VectorStoreService()
        self.model_name = model_name
        self.base_url = base_url

    def answer(
        self,
        question,
        db: Session,
        course_id=None,
        lecture_id=None,
        qa_mode: str = "open",
        mc_parsed=None,
    ):
        retrieval_question = question
        if qa_mode == "multiple_choice" and mc_parsed:
            retrieval_question = mc_parsed.get("retrieval_query") or question

        chunks, should_abstain, _reason = hybrid_retrieve_for_qa(
            self.vector_store,
            question=retrieval_question,
            course_id=course_id,
            lecture_id=lecture_id,
        )

        mc_opts = (mc_parsed.get("options") or []) if mc_parsed else []
        mc_ok = qa_mode == "multiple_choice" and mc_parsed and len(mc_opts) >= 2

        if not mc_ok and (should_abstain or not chunks):
            return {
                "answer": ABSTAIN_MESSAGE_HE if should_abstain else "לא נמצא מידע רלוונטי במסמכים.",
                "sources": [],
            }

        if mc_ok and (should_abstain or not chunks):
            chunks = []

        if mc_ok and chunks:
            chunks = order_chunks_for_mc(chunks, mc_parsed)

        context = "\n\n".join([c["text"] for c in chunks]) if chunks else ""

        if qa_mode == "multiple_choice" and mc_parsed:
            stem = (mc_parsed.get("stem") or "").strip()
            opts = mc_parsed.get("options") or []
            opts_block = "\n".join(f"{o['letter']}. {o['text']}" for o in opts)
            stem_display = stem if stem else "שאלת הבחירה המרובה שלהלן"
            mc_discipline = """
Two-step reasoning (do both before you write the final answer):
STEP A — Using ONLY Context, Question, and Options, pick exactly one best option letter (Hebrew א/ב/… or Latin A/B/…) or UNKNOWN.
STEP B — Write EXPLANATION that explains ONLY why that chosen option is correct. Do not argue for other options except at most one short contrast clause.

Hard rules (violation ⇒ set CORRECT to UNKNOWN or fix EXPLANATION before sending):
- The EXPLANATION must be fully consistent with CORRECT. Do not select one letter and explain a different one.
- Do not mention any numerical value, date, percentage, or money amount in EXPLANATION unless it appears in the selected option's text OR is strictly necessary from Context to justify that same option (and then cite only that supporting line of thought).
- Do not introduce facts, names, or numbers from Context that contradict the selected option, or that appear only under a different option's wording.
- If Context is conflicting between options or too thin to defend any letter, output CORRECT: UNKNOWN.

If the question and options are in Hebrew, write EXPLANATION in Hebrew. If they are in English, write EXPLANATION in English.

If CORRECT is UNKNOWN, EXPLANATION must be exactly this Hebrew sentence:
""" + ABSTAIN_MESSAGE_HE
            if context.strip():
                context_block = context
                ctx_rules = (
                    "You have retrieved course excerpts below. Prefer evidence that directly supports the chosen option.\n"
                    + mc_discipline
                )
            else:
                context_block = (
                    "(No course material excerpts were retrieved. Do not invent citations or unseen documents. "
                    "You may use the question stem and the options only: compare options, eliminate inconsistencies, "
                    "or apply obvious logic. If nothing is defensible, set CORRECT to UNKNOWN and in EXPLANATION "
                    "use exactly this Hebrew sentence:\n"
                    f"{ABSTAIN_MESSAGE_HE}\n"
                    "Otherwise follow STEP A and STEP B using only the stem and options.)"
                )
                ctx_rules = (
                    "There is no retrieved course text — do not claim material you do not have.\n"
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
{context_block}

Question:
{stem_display}

Options:
{opts_block}
"""
        else:
            prompt = f"""
Answer the question using ONLY the course material.

If the question is in Hebrew answer in Hebrew.
If the question is in English answer in English.

If the context does not contain enough information to answer the question, reply exactly with:
{ABSTAIN_MESSAGE_HE}

Context:
{context}

Question:
{question}
"""

        try:
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
            payload = response.json()
            answer = payload.get("response")
            if not answer:
                raise ValueError("Missing 'response' in model reply")
        except (requests_exceptions.ConnectionError, requests_exceptions.Timeout):
            return {
                "answer": "שירות המענה אינו זמין כרגע. נסה שוב בעוד רגע.",
                "sources": []
            }
        except Exception:
            return {
                "answer": "אירעה שגיאה בזמן יצירת התשובה.",
                "sources": []
            }

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
