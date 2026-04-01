"""
Validate and normalize LLM output for multiple-choice QA.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_NUM_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")

# When explanation cites numbers/grounds inconsistent with the chosen option + context
MC_FALLBACK_EXPLANATION_HE = (
    "ההסבר המקורי לא הוצג כי הוא כלל פרטים שאינם מתיישבים ישירות עם ניסוח האפשרות שנבחרה "
    "או עם החומר המצורף. האות שנבחרה נשמרה; מומלץ להצליב מול המקור."
)


def _valid_letters(options: List[Dict[str, Any]]) -> Set[str]:
    return {str(o.get("letter", "")).strip() for o in options if o.get("letter")}


def _extract_correct_value(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    for line in text.splitlines():
        m = re.match(r"^\s*CORRECT\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()
    m = re.search(r"(?is)CORRECT\s*:\s*([^\n\r]+)", text)
    if m:
        return m.group(1).strip()
    return None


def _extract_explanation(text: str) -> str:
    if not text or not text.strip():
        return ""
    m = re.search(r"(?is)EXPLANATION\s*:\s*(.*)$", text)
    if m:
        return m.group(1).strip()
    lines = text.splitlines()
    kept: List[str] = []
    for line in lines:
        if re.match(r"^\s*CORRECT\s*:\s*", line, re.IGNORECASE):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _normalize_candidate_letter(raw: str, option_script: str, valid: Set[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip().strip(" .()[]")
    if re.fullmatch(r"UNKNOWN", s, re.IGNORECASE):
        return "UNKNOWN"
    if option_script == "latin":
        s = s.upper()
    if s in valid:
        return s
    return None


def normalize_mc_model_output(raw: str, mc_parsed: Dict[str, Any]) -> Dict[str, str]:
    """
    Returns:
        correct_letter: one of the provided option letters, or UNKNOWN
        explanation: best-effort explanation text (never empty if raw had body)
    """
    options = mc_parsed.get("options") or []
    valid = _valid_letters(options)
    script = mc_parsed.get("option_script") or "hebrew"

    text = (raw or "").strip()
    explanation = _extract_explanation(text)
    if not explanation and text:
        explanation = _extract_explanation_fallback(text)

    correct_raw = _extract_correct_value(text)
    letter: Optional[str] = None
    if correct_raw is not None:
        letter = _normalize_candidate_letter(correct_raw, script, valid)

    if letter is None:
        letter = "UNKNOWN"

    if letter != "UNKNOWN" and letter not in valid:
        letter = "UNKNOWN"

    if not explanation:
        explanation = (
            "\n".join(
                ln
                for ln in text.splitlines()
                if not re.match(r"^\s*CORRECT\s*:\s*", ln, re.IGNORECASE)
            ).strip()
        )
    if not explanation:
        explanation = ""

    return {
        "correct_letter": letter,
        "explanation": explanation,
    }


def _extract_explanation_fallback(text: str) -> str:
    """When EXPLANATION: is missing, drop CORRECT line and use the rest."""
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        if re.match(r"^\s*CORRECT\s*:\s*", line, re.IGNORECASE):
            continue
        if re.match(r"^\s*EXPLANATION\s*:\s*$", line, re.IGNORECASE):
            continue
        if re.match(r"^\s*EXPLANATION\s*:\s*.+", line, re.IGNORECASE):
            m = re.match(r"^\s*EXPLANATION\s*:\s*(.+)$", line, re.IGNORECASE)
            if m and m.group(1).strip():
                out.append(m.group(1).strip())
            continue
        out.append(line)
    return "\n".join(out).strip()


def refine_mc_explanation_grounding(
    letter: str,
    explanation: str,
    mc_parsed: Dict[str, Any],
    context: str,
) -> Dict[str, str]:
    """
    If the explanation mentions digits that belong only to a non-selected option,
    or digits absent from stem/selected option/context, replace with a safe Hebrew line.
    Keeps CORRECT when the letter itself remains valid.
    """
    if letter == "UNKNOWN" or not (explanation or "").strip():
        return {"correct_letter": letter, "explanation": explanation or ""}

    opts = mc_parsed.get("options") or []
    selected = next((o for o in opts if str(o.get("letter", "")).strip() == letter), None)
    if not selected:
        return {"correct_letter": letter, "explanation": explanation}

    sel_text = str(selected.get("text") or "")
    stem = str(mc_parsed.get("stem") or "")
    ctx = context or ""

    exp_nums = set(_NUM_TOKEN.findall(explanation))
    if not exp_nums:
        return {"correct_letter": letter, "explanation": explanation}

    conflict = False
    for n in exp_nums:
        in_sel = n in sel_text
        in_stem = n in stem
        in_ctx = n in ctx
        in_other_not_sel = any(
            str(o.get("letter", "")).strip() != letter and n in str(o.get("text") or "")
            for o in opts
        )
        if in_other_not_sel and not in_sel:
            conflict = True
            break
        if not in_sel and not in_stem and not in_ctx:
            conflict = True
            break

    if not conflict:
        return {"correct_letter": letter, "explanation": explanation}

    logger.info(
        "mc_response_normalizer: explanation_replaced_for_grounding letter=%s",
        letter,
    )
    return {
        "correct_letter": letter,
        "explanation": MC_FALLBACK_EXPLANATION_HE,
    }
