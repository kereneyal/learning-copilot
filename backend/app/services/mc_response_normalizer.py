"""
Validate and normalize LLM output for multiple-choice QA.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_NUM_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
_TOKEN_RE = re.compile(r"[A-Za-z\u0590-\u05FF]{2,}")
_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")

_MC_SEMANTIC_MIN_SUPPORT = 0.24
_MC_SEMANTIC_CLEAR_MARGIN = 0.10
_MC_SEMANTIC_AMBIGUOUS_MARGIN = 0.06

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "than", "what",
    "which", "when", "where", "does", "is", "are", "was", "were", "can", "may",
    "על", "עם", "של", "זה", "זאת", "אחד", "אחת", "מה", "מי", "איך", "כאשר",
    "היא", "הוא", "הם", "הן", "גם", "לא", "כן", "או", "אם", "אך", "כל", "יותר",
}

# When explanation cites numbers/grounds inconsistent with the chosen option + context
MC_FALLBACK_EXPLANATION_HE = (
    "ההסבר המקורי לא הוצג כי הוא כלל פרטים שאינם מתיישבים ישירות עם ניסוח האפשרות שנבחרה "
    "או עם החומר המצורף. האות שנבחרה נשמרה; מומלץ להצליב מול המקור."
)
MC_FALLBACK_EXPLANATION_EN = (
    "The original explanation was replaced because it included details that do not align "
    "directly with the selected option or the provided context."
)
MC_UNKNOWN_EXPLANATION_HE = "לא נמצא עיגון מספיק בהקשר כדי לבחור תשובה אחת בביטחון."
MC_UNKNOWN_EXPLANATION_EN = "There is not enough grounded support in the context to choose one answer confidently."


def _valid_letters(options: List[Dict[str, Any]]) -> Set[str]:
    return {str(o.get("letter", "")).strip() for o in options if o.get("letter")}


def _contains_hebrew(text: str) -> bool:
    return bool(text and _HEBREW_RE.search(text))


def _normalize_token(token: str) -> str:
    t = (token or "").strip().lower()
    if not t:
        return ""
    if _contains_hebrew(t):
        if len(t) > 4 and t[0] in "והבכלמש":
            t = t[1:]
        for suffix in ("יות", "יות", "ות", "ים", "ה", "ת", "י"):
            if len(t) > 4 and t.endswith(suffix):
                t = t[: -len(suffix)]
                break
    else:
        for suffix in ("ing", "ed", "es", "s"):
            if len(t) > 4 and t.endswith(suffix):
                t = t[: -len(suffix)]
                break
    return t


def _semantic_tokens(text: str) -> Set[str]:
    out: Set[str] = set()
    for raw in _TOKEN_RE.findall(text or ""):
        norm = _normalize_token(raw)
        if len(norm) < 2 or norm in _STOPWORDS:
            continue
        out.add(norm)
    return out


def _context_segments(text: str) -> List[str]:
    if not text:
        return []
    raw_parts = re.split(r"[\n\r]+|(?<=[.!?।])\s+", text)
    parts = [p.strip() for p in raw_parts if p and p.strip()]
    return parts or [text.strip()]


def _token_f1(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    if overlap == 0:
        return 0.0
    precision = overlap / len(b)
    recall = overlap / len(a)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _string_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _score_option_support(
    option_text: str,
    explanation: str,
    context: str,
) -> Tuple[float, str]:
    option_tokens = _semantic_tokens(option_text)
    if not option_tokens or not context.strip():
        return 0.0, ""

    expl_tokens = _semantic_tokens(explanation)
    full_context_tokens = _semantic_tokens(context)
    overall_overlap = len(option_tokens & full_context_tokens) / max(len(option_tokens), 1)

    best_segment_score = 0.0
    best_expl_support = 0.0
    best_segment = ""

    for segment in _context_segments(context):
        seg_tokens = _semantic_tokens(segment)
        if not seg_tokens:
            continue
        overlap_score = _token_f1(option_tokens, seg_tokens)
        phrase_score = _string_similarity(option_text, segment)
        expl_score = _token_f1(expl_tokens, seg_tokens) if expl_tokens else 0.0
        seg_score = 0.65 * overlap_score + 0.35 * phrase_score
        if seg_score > best_segment_score:
            best_segment_score = seg_score
            best_segment = segment
        best_expl_support = max(best_expl_support, expl_score)

    final_score = (
        0.60 * best_segment_score
        + 0.25 * overall_overlap
        + 0.15 * best_expl_support
    )
    return final_score, best_segment


def _build_grounded_explanation(
    option_text: str,
    supporting_segment: str,
    prefer_hebrew: bool,
) -> str:
    snippet = (supporting_segment or "").strip()
    if len(snippet) > 180:
        snippet = snippet[:177].rstrip() + "..."
    if prefer_hebrew:
        if snippet:
            return f"ההקשר מתאר ש{snippet}, ולכן האפשרות המתאימה היא \"{option_text}\"."
        return f"האפשרות \"{option_text}\" נתמכת במשמעות שעולה מההקשר."
    if snippet:
        return f"The context indicates that {snippet}, so the best-supported option is \"{option_text}\"."
    return f'The option "{option_text}" is the best match for the meaning of the context.'


def _semantic_select_letter(
    model_letter: str,
    explanation: str,
    mc_parsed: Dict[str, Any],
    context: str,
) -> Dict[str, Any]:
    options = mc_parsed.get("options") or []
    if not options or not (context or "").strip():
        return {
            "correct_letter": "UNKNOWN",
            "explanation": "",
            "scores": {},
            "reason": "no_context",
        }

    prefer_hebrew = _contains_hebrew((mc_parsed.get("stem") or "") + " " + context)
    scored: List[Tuple[float, str, str, str]] = []
    for opt in options:
        letter = str(opt.get("letter", "")).strip()
        text = str(opt.get("text") or "")
        score, segment = _score_option_support(text, explanation, context)
        scored.append((score, letter, text, segment))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score, top_letter, top_text, top_segment = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = top_score - second_score
    scores_map = {letter: round(score, 3) for score, letter, _, _ in scored}

    logger.info(
        "mc.semantic_scores top=%s top_score=%.3f second_score=%.3f margin=%.3f scores=%s",
        top_letter,
        top_score,
        second_score,
        margin,
        scores_map,
    )

    if top_score < _MC_SEMANTIC_MIN_SUPPORT:
        return {
            "correct_letter": "UNKNOWN",
            "explanation": "",
            "scores": scores_map,
            "reason": "no_supported_option",
        }

    if margin < _MC_SEMANTIC_AMBIGUOUS_MARGIN:
        return {
            "correct_letter": "UNKNOWN",
            "explanation": "",
            "scores": scores_map,
            "reason": "ambiguous_close_scores",
        }

    if model_letter == top_letter:
        return {
            "correct_letter": top_letter,
            "explanation": _build_grounded_explanation(top_text, top_segment, prefer_hebrew),
            "scores": scores_map,
            "reason": "model_supported",
        }

    if model_letter == "UNKNOWN" and margin >= _MC_SEMANTIC_CLEAR_MARGIN:
        return {
            "correct_letter": top_letter,
            "explanation": _build_grounded_explanation(top_text, top_segment, prefer_hebrew),
            "scores": scores_map,
            "reason": "fallback_clear_winner",
        }

    chosen_score = next((score for score, letter, _, _ in scored if letter == model_letter), 0.0)
    if chosen_score >= _MC_SEMANTIC_MIN_SUPPORT and (top_score - chosen_score) < _MC_SEMANTIC_CLEAR_MARGIN:
        chosen_text = next((text for score, letter, text, _ in scored if letter == model_letter), "")
        chosen_segment = next((segment for score, letter, _, segment in scored if letter == model_letter), "")
        return {
            "correct_letter": model_letter,
            "explanation": _build_grounded_explanation(chosen_text, chosen_segment, prefer_hebrew),
            "scores": scores_map,
            "reason": "model_kept_supported",
        }

    if margin >= _MC_SEMANTIC_CLEAR_MARGIN:
        return {
            "correct_letter": top_letter,
            "explanation": _build_grounded_explanation(top_text, top_segment, prefer_hebrew),
            "scores": scores_map,
            "reason": "switched_to_clear_winner",
        }

    return {
        "correct_letter": "UNKNOWN",
        "explanation": "",
        "scores": scores_map,
        "reason": "ambiguous_after_validation",
    }


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
    Apply semantic grounding for MC answers:
    - accept a clearly supported option even if wording differs
    - keep UNKNOWN only for unsupported or ambiguous contexts
    - replace brittle explanations with a context-meaning explanation when needed
    """
    semantic = _semantic_select_letter(letter, explanation, mc_parsed, context)
    resolved_letter = semantic["correct_letter"]
    resolved_explanation = semantic["explanation"] or explanation or ""

    if resolved_letter == "UNKNOWN":
        prefer_hebrew = _contains_hebrew((mc_parsed.get("stem") or "") + " " + context)
        return {
            "correct_letter": "UNKNOWN",
            "explanation": MC_UNKNOWN_EXPLANATION_HE if prefer_hebrew else MC_UNKNOWN_EXPLANATION_EN,
        }

    opts = mc_parsed.get("options") or []
    selected = next((o for o in opts if str(o.get("letter", "")).strip() == resolved_letter), None)
    if not selected:
        return {"correct_letter": resolved_letter, "explanation": resolved_explanation}

    sel_text = str(selected.get("text") or "")
    stem = str(mc_parsed.get("stem") or "")
    ctx = context or ""

    exp_nums = set(_NUM_TOKEN.findall(resolved_explanation))
    if not exp_nums:
        return {"correct_letter": resolved_letter, "explanation": resolved_explanation}

    conflict = False
    for n in exp_nums:
        in_sel = n in sel_text
        in_stem = n in stem
        in_ctx = n in ctx
        in_other_not_sel = any(
            str(o.get("letter", "")).strip() != resolved_letter and n in str(o.get("text") or "")
            for o in opts
        )
        if in_other_not_sel and not in_sel:
            conflict = True
            break
        if not in_sel and not in_stem and not in_ctx:
            conflict = True
            break

    if not conflict:
        return {"correct_letter": resolved_letter, "explanation": resolved_explanation}

    logger.info(
        "mc_response_normalizer: explanation_replaced_for_grounding letter=%s reason=%s",
        resolved_letter,
        semantic.get("reason"),
    )
    prefer_hebrew = _contains_hebrew(stem + " " + ctx)
    return {
        "correct_letter": resolved_letter,
        "explanation": MC_FALLBACK_EXPLANATION_HE if prefer_hebrew else MC_FALLBACK_EXPLANATION_EN,
    }
