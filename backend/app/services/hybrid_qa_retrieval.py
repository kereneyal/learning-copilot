"""
Hybrid retrieval for QA: lexical candidates from scoped Chroma scan, then vector search,
merge/dedupe, rerank, optional domain-term gate, abstention when not grounded.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Substrings: if present in the user question, require at least one hit in final context chunks.
DOMAIN_TERMS_HE = [
    "אורגנים",
    "דירקטוריון",
    "אסיפה כללית",
    "מנכ\"ל",
    "מנכ״ל",
    "ממשל תאגידי",
]

# If the question uses these surface forms, apply the same strict domain gate as the canonical term.
QUESTION_PHRASE_TO_CANONICAL = {
    "האסיפה הכללית": "אסיפה כללית",
    "הדירקטוריון": "דירקטוריון",
    "ועד הדירקטוריון": "דירקטוריון",
    "האורגנים": "אורגנים",
}

# Chunk text may satisfy the gate for a canonical term via these short alternates (no new deps).
CHUNK_ALIASES_BY_CANONICAL = {
    "אסיפה כללית": ("האסיפה הכללית",),
    "דירקטוריון": ("הדירקטוריון", "ועד הדירקטוריון"),
    "אורגנים": ("האורגנים",),
    "מנכ\"ל": ("מנכ״ל", "המנכ\"ל", "המנכ״ל"),
    "מנכ״ל": ("מנכ\"ל", "המנכ\"ל", "המנכ״ל"),
    "ממשל תאגידי": ("ממשל חברות",),
}

# Substrings in chunk text: boost lexical rerank; also used as "anchor" when question only mentions אורגנים.
_GOVERNANCE_LEXICAL_MARKERS = (
    "דירקטוריון",
    "אסיפה כללית",
    "מנכ\"ל",
    "מנכ״ל",
    "רואה חשבון",
    "מבקר פנימי",
    "ועדת ביקורת",
    "ועדת תגמול",
    "ממשל תאגידי",
    "ממשל חברות",
    "האסיפה הכללית",
    "הדירקטוריון",
)

_GOVERNANCE_MARKER_BONUS = 2.2
_GOVERNANCE_BONUS_CAP = 14.0

ABSTAIN_MESSAGE_HE = (
    "לא מצאתי מקור מספיק רלוונטי כדי לענות בביטחון. נסה לנסח מחדש או חפש במסמכים."
)

# Scoped fetch for substring lexical pass; lexical weight favors exact/structural hits over raw embedding.
_LEX_MAX_FETCH = 720
_VECTOR_CANDIDATES = 28
_FINAL_CONTEXT_CHUNKS = 6
_FINAL_SOURCE_CHUNKS = 5

# Rerank: exact/substring and governance markers should outrank broad semantic similarity.
_LEX_WEIGHT = 0.52
_VEC_WEIGHT = 0.48


def _norm_text(s: str) -> str:
    if not s:
        return ""
    return s.strip()


def domain_terms_in_question(question: str) -> List[str]:
    """Unique canonical domain markers triggered by the question (strict gate applies)."""
    q = question or ""
    out: List[str] = []
    seen: Set[str] = set()
    for t in DOMAIN_TERMS_HE:
        if t in q and t not in seen:
            out.append(t)
            seen.add(t)
    for syn, canon in QUESTION_PHRASE_TO_CANONICAL.items():
        if syn in q and canon not in seen:
            out.append(canon)
            seen.add(canon)
    return out


def _organisms_only_domain(required_canonicals: List[str]) -> bool:
    """Question triggered only 'אורגנים' — require a governance-structure anchor in the chunk."""
    return set(required_canonicals) == {"אורגנים"}


def _governance_structure_anchor(text: str) -> bool:
    blob = text or ""
    return any(m in blob for m in _GOVERNANCE_LEXICAL_MARKERS)


def _governance_chunk_bonus(text: str) -> float:
    """Extra lexical score when chunk mentions concrete governance bodies (helps board-summary docs)."""
    if not text:
        return 0.0
    bonus = 0.0
    for m in _GOVERNANCE_LEXICAL_MARKERS:
        if m in text:
            bonus += _GOVERNANCE_MARKER_BONUS
    return min(bonus, _GOVERNANCE_BONUS_CAP)


def _chunk_matches_domain_requirements(text: str, required_canonicals: List[str]) -> bool:
    """Strict: at least one required canonical (or its chunk alias) must appear in the chunk."""
    if not required_canonicals:
        return True
    blob = text or ""
    for canon in set(required_canonicals):
        if canon in blob:
            if _organisms_only_domain(required_canonicals) and canon == "אורגנים":
                return _governance_structure_anchor(blob)
            return True
        for alt in CHUNK_ALIASES_BY_CANONICAL.get(canon, ()):
            if alt in blob:
                if _organisms_only_domain(required_canonicals) and canon == "אורגנים":
                    return _governance_structure_anchor(blob)
                return True
    return False


def _tokenize_query(question: str) -> List[str]:
    q = _norm_text(question)
    if not q:
        return []
    q = re.sub(r"[^\w\s\u0590-\u05FF]", " ", q)
    parts = [p for p in q.split() if len(p) >= 2]
    return parts[:40]


def _chunk_key(c: Dict[str, Any]) -> Tuple[str, Any]:
    return (str(c.get("document_id") or ""), c.get("chunk_index"))


def _lexical_score(text: str, tokens: Set[str], phrases_in_q: List[str]) -> float:
    if not text:
        return 0.0
    t = text
    score = 0.0
    for ph in phrases_in_q:
        if ph and ph in t:
            score += 3.0
    low = t.lower()
    for tok in tokens:
        if len(tok) < 2:
            continue
        if tok.lower() in low or tok in t:
            score += 1.0
    return score


def _normalize_scores(scores: List[float]) -> List[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi <= lo:
        return [1.0 if scores else 0.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def _distance_to_sim(d: Optional[float]) -> float:
    if d is None:
        return 0.5
    try:
        d = float(d)
    except (TypeError, ValueError):
        return 0.5
    return 1.0 / (1.0 + max(0.0, d))


def merge_and_rerank(
    lexical_chunks: List[Dict[str, Any]],
    vector_chunks: List[Dict[str, Any]],
    question_tokens: Set[str],
    phrases_in_q: List[str],
    domain_query: bool,
) -> List[Dict[str, Any]]:
    merged: Dict[Tuple[str, Any], Dict[str, Any]] = {}

    for c in lexical_chunks:
        k = _chunk_key(c)
        merged[k] = {**c, "_lex": float(c.get("_lex") or 0.0), "_dist": c.get("_distance")}

    for c in vector_chunks:
        k = _chunk_key(c)
        if k in merged:
            prev = merged[k]
            merged[k] = {
                **prev,
                **{kk: vv for kk, vv in c.items() if vv is not None and kk not in prev},
                "_lex": max(float(prev.get("_lex") or 0), float(c.get("_lex") or 0)),
                "_dist": c.get("_distance") if c.get("_distance") is not None else prev.get("_dist"),
            }
        else:
            txt = c.get("text") or ""
            lex = _lexical_score(txt, question_tokens, phrases_in_q)
            if domain_query:
                lex += _governance_chunk_bonus(txt)
            merged[k] = {**c, "_lex": lex, "_dist": c.get("_distance")}

    items = list(merged.values())
    if not items:
        return []

    lex_vals = [float(x.get("_lex") or 0) for x in items]
    lex_norm = _normalize_scores(lex_vals)
    vec_sims = [_distance_to_sim(x.get("_distance")) for x in items]

    for i, it in enumerate(items):
        combined = _LEX_WEIGHT * lex_norm[i] + _VEC_WEIGHT * vec_sims[i]
        it["_rerank_score"] = combined

    items.sort(key=lambda x: float(x.get("_rerank_score") or 0), reverse=True)
    return items


def _select_top_chunks(ranked: List[Dict[str, Any]], required_terms: List[str], max_n: int) -> List[Dict[str, Any]]:
    """Prefer rerank order; if domain terms required, only keep chunks that pass strict domain match."""
    if not ranked:
        return []
    if not required_terms:
        return ranked[:max_n]
    matched = [
        c
        for c in ranked
        if _chunk_matches_domain_requirements(_norm_text(c.get("text") or ""), required_terms)
    ]
    return matched[:max_n]


def hybrid_retrieve_for_qa(
    vector_store,
    question: str,
    course_id: Optional[str],
    lecture_id: Optional[str],
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Returns (chunks_for_context_and_sources, should_abstain, abstain_reason_or_empty).
    Chunks are stripped of internal _keys for prompt/sources where needed by caller.
    """
    q = _norm_text(question)
    tokens_list = _tokenize_query(q)
    tokens_set = set(tokens_list)

    phrases_in_q: List[str] = []
    for ph in DOMAIN_TERMS_HE:
        if ph in q:
            phrases_in_q.append(ph)
    for syn, canon in QUESTION_PHRASE_TO_CANONICAL.items():
        if syn in q:
            phrases_in_q.append(syn)
            if canon not in phrases_in_q:
                phrases_in_q.append(canon)

    required_domain = domain_terms_in_question(q)

    lex_chunks: List[Dict[str, Any]] = []
    lex_enabled = bool(course_id)
    raw_fetched = 0
    if course_id:
        raw = vector_store.fetch_chunks_for_scope(
            course_id=course_id,
            lecture_id=lecture_id,
            limit=_LEX_MAX_FETCH,
        )
        raw_fetched = len(raw)
        for row in raw:
            txt = row.get("text") or ""
            base_lex = _lexical_score(txt, tokens_set, phrases_in_q)
            gov_bonus = _governance_chunk_bonus(txt) if required_domain else 0.0
            lex = base_lex + gov_bonus
            if lex <= 0:
                continue
            meta = row.get("metadata") or {}
            lex_chunks.append(
                {
                    "text": txt,
                    "snippet": (txt[:300] if txt else ""),
                    "course_id": meta.get("course_id"),
                    "lecture_id": meta.get("lecture_id"),
                    "document_id": meta.get("document_id"),
                    "chunk_index": meta.get("chunk_index"),
                    "_lex": lex,
                    "_distance": None,
                }
            )
        lex_chunks.sort(key=lambda x: float(x.get("_lex") or 0), reverse=True)
        lex_chunks = lex_chunks[: max(50, _VECTOR_CANDIDATES)]

    try:
        vec_chunks = vector_store.search_with_distances(
            query=q,
            course_id=course_id,
            lecture_id=lecture_id,
            top_k=_VECTOR_CANDIDATES,
        )
    except Exception:
        vec_chunks = []

    ranked = merge_and_rerank(
        lex_chunks,
        vec_chunks,
        tokens_set,
        phrases_in_q,
        domain_query=bool(required_domain),
    )

    if not ranked:
        logger.info(
            "hybrid_qa_retrieval: course_id=%s lecture_id=%s lexical_enabled=%s "
            "chunks_fetched=%s lex_candidates=%s vec_candidates=%s ranked=0 -> abstain no_candidates",
            course_id,
            lecture_id,
            lex_enabled,
            raw_fetched,
            len(lex_chunks),
            len(vec_chunks),
        )
        return [], True, "no_candidates"

    top = _select_top_chunks(ranked, required_domain, _FINAL_CONTEXT_CHUNKS)

    if required_domain and not top:
        logger.info(
            "hybrid_qa_retrieval: course_id=%s lecture_id=%s lexical_enabled=%s "
            "chunks_fetched=%s lex_candidates=%s vec_candidates=%s ranked=%s domain_gate -> abstain",
            course_id,
            lecture_id,
            lex_enabled,
            raw_fetched,
            len(lex_chunks),
            len(vec_chunks),
            len(ranked),
        )
        return [], True, "domain_gate"

    if not top:
        logger.info(
            "hybrid_qa_retrieval: course_id=%s lecture_id=%s lexical_enabled=%s "
            "chunks_fetched=%s lex_candidates=%s vec_candidates=%s -> abstain no_candidates",
            course_id,
            lecture_id,
            lex_enabled,
            raw_fetched,
            len(lex_chunks),
            len(vec_chunks),
        )
        return [], True, "no_candidates"

    # Strip internal scoring keys for downstream use
    clean: List[Dict[str, Any]] = []
    for c in top:
        clean.append(
            {
                "text": c.get("text"),
                "snippet": c.get("snippet") or (c.get("text") or "")[:300],
                "course_id": c.get("course_id"),
                "lecture_id": c.get("lecture_id"),
                "document_id": c.get("document_id"),
                "chunk_index": c.get("chunk_index"),
            }
        )

    logger.info(
        "hybrid_qa_retrieval: course_id=%s lecture_id=%s lexical_enabled=%s "
        "chunks_fetched=%s lex_candidates=%s vec_candidates=%s ranked=%s final_selected=%s",
        course_id,
        lecture_id,
        lex_enabled,
        raw_fetched,
        len(lex_chunks),
        len(vec_chunks),
        len(ranked),
        [(c.get("document_id"), c.get("chunk_index")) for c in clean],
    )

    return clean, False, ""
