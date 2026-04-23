"""
Hybrid retrieval for QA: lexical candidates from scoped Chroma scan, then vector search,
merge/dedupe, rerank, optional domain-term gate, abstention when not grounded.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain gate — opt-in, off by default for non-governance deployments.
# Set DOMAIN_GATE_ENABLED=true to activate strict term-based filtering.
# ---------------------------------------------------------------------------
_DOMAIN_GATE_ENABLED = os.getenv("DOMAIN_GATE_ENABLED", "false").lower() in ("1", "true", "yes")

# Substrings: if present in the user question AND domain gate is enabled,
# require at least one hit in final context chunks.
DOMAIN_TERMS_HE = [
    "אורגנים",
    "דירקטוריון",
    "אסיפה כללית",
    'מנכ"ל',
    "מנכ״ל",
    "ממשל תאגידי",
]

# Surface-form → canonical normalisation (question side only).
QUESTION_PHRASE_TO_CANONICAL = {
    "האסיפה הכללית": "אסיפה כללית",
    "הדירקטוריון": "דירקטוריון",
    "ועד הדירקטוריון": "דירקטוריון",
    "האורגנים": "אורגנים",
}

# Chunk-text aliases per canonical term.
CHUNK_ALIASES_BY_CANONICAL = {
    "אסיפה כללית": ("האסיפה הכללית",),
    "דירקטוריון": ("הדירקטוריון", "ועד הדירקטוריון"),
    "אורגנים": ("האורגנים",),
    'מנכ"ל': ('מנכ״ל', 'המנכ"ל', "המנכ״ל"),
    "מנכ״ל": ('מנכ"ל', 'המנכ"ל', "המנכ״ל"),
    "ממשל תאגידי": ("ממשל חברות",),
}

# Governance markers used for lexical scoring bonus (not for gating).
_GOVERNANCE_LEXICAL_MARKERS = (
    "דירקטוריון",
    "אסיפה כללית",
    'מנכ"ל',
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

# ---------------------------------------------------------------------------
# Multilingual support — English queries are expanded with Hebrew equivalents
# so that English questions retrieve Hebrew course content correctly.
# ---------------------------------------------------------------------------
_EN_ALPHA_RE = re.compile(r"[a-zA-Z]")
_HE_CHAR_RE = re.compile(r"[\u0590-\u05FF]")
_WORD_RE = re.compile(r"[A-Za-z]{2,}|[\u0590-\u05FF]{2,}")

_DEFINITION_RE = re.compile(
    r"^("
    r"מה\s+זה\s+"
    r"|מה\s+ה-"
    r"|מה\s+(הוא|היא)\s+"
    r"|הגדר\s+את\s+"
    r"|מה\s+המשמעות\s+"
    r"|מה\s+פירוש\s+"
    r"|what\s+is\b"
    r"|define\b"
    r"|explain\s+the\s+term\b"
    r")",
    re.IGNORECASE,
)

_ACRONYM_RE = re.compile(
    r"^("
    r"מה\s+פירוש\s+ראשי\s+התיבות\b"
    r"|מה\s+ראשי\s+התיבות\b"
    r"|what\s+does\s+\S+\s+stand\s+for\b"
    r"|what\s+is\s+the\s+(?:full\s+)?acronym\b"
    r")",
    re.IGNORECASE,
)

# Chunks that contain an acronym from the question AND a definition marker
# (e.g. "ראשי תיבות") are boosted so definition chunks rank first.
_ACRONYM_DEF_MARKERS = (
    "ראשי תיבות", "הוא ראשי", "היא ראשי", 'ר"ת', "ר״ת",
    "stands for", "acronym for", "short for", "is defined as",
)
_ACRONYM_DEFINITION_BONUS = 3.5
_ACRONYM_EXACT_TOKEN_BONUS = 1.2
_ACRONYM_EXPANSION_BONUS = 4.5

_EN_DEFINITION_EXPANSIONS = (
    "definition",
    "stands for",
    "acronym",
)
_HE_DEFINITION_EXPANSIONS = (
    "ראשי תיבות",
    "פירוש",
    "הגדרה",
)
_DEFINITION_STOPWORDS = {
    "what", "does", "stand", "for", "define", "term", "the", "this", "that",
    "מה", "זה", "פירוש", "ראשי", "התיבות", "הגדרה", "של", "עם", "הוא", "היא",
    "stands", "acronym", "definition", "defined", "as", "short",
}

ABSTAIN_MESSAGE_HE = (
    "לא מצאתי מקור מספיק רלוונטי כדי לענות בביטחון. נסה לנסח מחדש או חפש במסמכים."
)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
# FIX: increased from 720 to 1500 — prevents silent under-retrieval when a
# course has many documents.  Chroma's get() is a sequential disk scan; at
# ~300 µs/chunk this stays well under 500 ms for typical course sizes.
_LEX_MAX_FETCH = 1500

_VECTOR_CANDIDATES = 28
_FINAL_CONTEXT_CHUNKS = 6

_LEX_WEIGHT = 0.52
_VEC_WEIGHT = 0.48


def _norm_text(s: str) -> str:
    if not s:
        return ""
    return s.strip()


def _is_english_dominant(text: str) -> bool:
    """True when the text has more English alpha chars than Hebrew chars (min 4 English)."""
    en = len(_EN_ALPHA_RE.findall(text))
    he = len(_HE_CHAR_RE.findall(text))
    return en > he and en >= 4


def _is_hebrew_dominant(text: str) -> bool:
    he = len(_HE_CHAR_RE.findall(text))
    en = len(_EN_ALPHA_RE.findall(text))
    return he >= en and he >= 2


def _detect_question_language(text: str) -> str:
    if _is_english_dominant(text):
        return "en"
    if _is_hebrew_dominant(text):
        return "he"
    return "mixed"


def _is_definition_question(question: str) -> bool:
    return bool(_DEFINITION_RE.match(question.strip()))


def _is_acronym_question(question: str) -> bool:
    return bool(_ACRONYM_RE.match(question.strip()))


def _extract_key_term(question: str) -> str:
    """
    Strip question scaffolding and return the core concept.
    "What does VUCA stand for?" → "VUCA"
    "What is agility?" → "agility"
    """
    q = question.strip()
    he_match = re.match(
        r"^(?:"
        r"מה\s+זה\s+"
        r"|מה\s+פירוש\s+ראשי\s+התיבות\s+"
        r"|מה\s+פירוש\s+"
        r"|מה\s+המשמעות\s+של\s+"
        r"|מה\s+ראשי\s+התיבות\s+של\s+"
        r"|הגדר\s+את\s+"
        r")(.+)$",
        q,
    )
    if he_match:
        q = he_match.group(1).strip()
        return re.sub(r"[?!.,;:]+$", "", q).strip()
    q = re.sub(
        r"^(?:"
        r"what\s+is\s+(?:the\s+)?(?:full\s+)?acronym\s+(?:for\s+|of\s+)?|"  # most specific first
        r"what\s+(?:is|does|are)\s+(?:an?\s+|the\s+)?|"
        r"define\s+(?:the\s+term\s+)?|"
        r"explain\s+(?:the\s+term\s+)?"
        r")",
        "", q, flags=re.IGNORECASE,
    )
    m = re.match(r"(.+?)\s+stand\s+for\b", q, re.IGNORECASE)
    if m:
        q = m.group(1).strip()
    return re.sub(r"[?!.,;]+$", "", q).strip()


def _contains_exact_token(text: str, token: str) -> bool:
    if not text or not token:
        return False
    if re.match(r"^[A-Za-z0-9_-]+$", token):
        return bool(re.search(rf"\b{re.escape(token)}\b", text))
    return token in text


def _extract_expansion_terms(text: str) -> Set[str]:
    if not text:
        return set()
    terms: Set[str] = set()
    lowered = text.lower()
    marker_positions = [lowered.find(marker.lower()) for marker in _ACRONYM_DEF_MARKERS if lowered.find(marker.lower()) >= 0]
    eq_pos = text.find("=")
    if eq_pos >= 0:
        marker_positions.append(eq_pos)
    for start in marker_positions:
        window = text[start:start + 220]
        for word in _WORD_RE.findall(window):
            norm = word.lower()
            if len(norm) < 3 or norm in _DEFINITION_STOPWORDS:
                continue
            terms.add(norm)
    return terms


def _acronym_definition_bonus(
    text: str,
    question_tokens: Set[str],
    expected_terms: Optional[Set[str]] = None,
) -> float:
    """
    Extra score for chunks that contain an acronym from the question AND a
    definition-expansion marker.  These are the chunks that spell out what each
    letter stands for — exactly what a definition question needs.
    """
    if not text:
        return 0.0
    acronyms = {t for t in question_tokens if re.match(r"^[A-Z]{2,}$", t)}
    if not acronyms:
        return 0.0
    best_bonus = 0.0
    lowered = text.lower()
    for acronym in acronyms:
        if not _contains_exact_token(text, acronym):
            continue
        bonus = _ACRONYM_EXACT_TOKEN_BONUS
        has_marker = any(marker.lower() in lowered for marker in _ACRONYM_DEF_MARKERS) or "=" in text
        if has_marker:
            bonus += _ACRONYM_DEFINITION_BONUS
        expansion_terms = _extract_expansion_terms(text)
        matched_expected = 0
        if expected_terms:
            matched_expected = sum(1 for term in expected_terms if term in expansion_terms or re.search(rf"\b{re.escape(term)}\b", lowered))
        if matched_expected >= 2 or (has_marker and len(expansion_terms) >= 4):
            bonus += _ACRONYM_EXPANSION_BONUS
        best_bonus = max(best_bonus, bonus)
    return best_bonus


def _build_retrieval_queries(question: str) -> Dict[str, Any]:
    q = _norm_text(question)
    language = _detect_question_language(q)
    is_definition = _is_definition_question(q)
    is_acronym = _is_acronym_question(q)
    definition_mode = is_definition or is_acronym
    key_term = _extract_key_term(q) if definition_mode else ""

    queries: List[str] = []

    def add_query(query: str) -> None:
        query = _norm_text(query)
        if query and query not in queries:
            queries.append(query)

    add_query(q)

    if definition_mode and key_term:
        add_query(f"{key_term} definition")
        add_query(f"{key_term} stands for")
        add_query(f"{key_term} acronym")
        add_query(f"{key_term} ראשי תיבות")
        add_query(f"{key_term} פירוש")
        add_query(f"{key_term} הגדרה")

        if language == "en":
            add_query(f"מה זה {key_term}")
            add_query(f"מה פירוש {key_term}")
            add_query(f"מה פירוש ראשי התיבות {key_term}")
        elif language == "he":
            add_query(f"What is {key_term}?")
            add_query(f"Define {key_term}")
            add_query(f"What does {key_term} stand for?")

    expected_terms = {
        word.lower()
        for query in queries
        for word in _WORD_RE.findall(query)
        if len(word) >= 3 and word.lower() not in _DEFINITION_STOPWORDS
    }
    if key_term:
        expected_terms.discard(key_term.lower())

    return {
        "language": language,
        "definition_mode": definition_mode,
        "is_acronym": is_acronym,
        "key_term": key_term,
        "queries": queries,
        "expected_terms": expected_terms,
    }


def domain_terms_in_question(question: str) -> List[str]:
    """Unique canonical domain markers triggered by the question."""
    if not _DOMAIN_GATE_ENABLED:
        return []
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


def _chunk_matches_domain_requirements(text: str, required_canonicals: List[str]) -> bool:
    """
    Strict: at least one required canonical (or its chunk alias) must appear in the chunk.
    Only called when _DOMAIN_GATE_ENABLED=true and required_canonicals is non-empty.
    """
    if not required_canonicals:
        return True
    blob = text or ""
    for canon in set(required_canonicals):
        if canon in blob:
            return True
        for alt in CHUNK_ALIASES_BY_CANONICAL.get(canon, ()):
            if alt in blob:
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


def _governance_chunk_bonus(text: str) -> float:
    """Extra lexical score when chunk mentions concrete governance bodies."""
    if not text:
        return 0.0
    bonus = 0.0
    for m in _GOVERNANCE_LEXICAL_MARKERS:
        if m in text:
            bonus += _GOVERNANCE_MARKER_BONUS
    return min(bonus, _GOVERNANCE_BONUS_CAP)


def _normalize_scores(scores: List[float]) -> List[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    # FIX: when all lexical scores are zero (no token matches), return zeros —
    # not ones. The old code returned 1.0 for all-tied, giving every vector
    # candidate a free +0.52 lexical bonus and breaking combined ranking.
    if hi <= lo:
        return [0.0 for _ in scores]
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
    expected_terms: Optional[Set[str]] = None,
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

    # Boost chunks that contain both the question acronym and a definition
    # marker (e.g. "ראשי תיבות").  Applied before normalisation so the boost
    # survives the min-max scaling step.
    acronym_boosted = 0
    for it in items:
        bonus = _acronym_definition_bonus(
            it.get("text") or "",
            question_tokens,
            expected_terms=expected_terms,
        )
        if bonus:
            it["_lex"] = float(it.get("_lex") or 0) + bonus
            acronym_boosted += 1
    if acronym_boosted:
        logger.info("rerank.acronym_boost applied=True boosted_chunks=%d", acronym_boosted)

    lex_vals = [float(x.get("_lex") or 0) for x in items]
    lex_norm = _normalize_scores(lex_vals)
    vec_sims = [_distance_to_sim(x.get("_distance")) for x in items]

    # Log score distribution to help diagnose reranking problems.
    logger.debug(
        "rerank.distribution n=%d lex_raw=[%.2f..%.2f] vec_sim=[%.3f..%.3f] acronym_boosted=%d",
        len(items),
        min(lex_vals, default=0.0),
        max(lex_vals, default=0.0),
        min(vec_sims, default=0.0),
        max(vec_sims, default=0.0),
        acronym_boosted,
    )

    for i, it in enumerate(items):
        combined = _LEX_WEIGHT * lex_norm[i] + _VEC_WEIGHT * vec_sims[i]
        it["_rerank_score"] = combined

    items.sort(key=lambda x: float(x.get("_rerank_score") or 0), reverse=True)

    # Log top-6 candidates for post-mortem debugging.
    for rank, it in enumerate(items[:6]):
        logger.debug(
            "rerank.candidate rank=%d combined=%.3f lex_raw=%.2f lex_norm=%.3f "
            "vec_sim=%.3f doc=%s idx=%s snippet=%r",
            rank,
            float(it.get("_rerank_score") or 0),
            float(it.get("_lex") or 0),
            lex_norm[items.index(it)] if rank < len(lex_norm) else 0.0,
            _distance_to_sim(it.get("_distance")),
            it.get("document_id"),
            it.get("chunk_index"),
            (it.get("text") or "")[:60],
        )

    return items


def _select_top_chunks(ranked: List[Dict[str, Any]], required_terms: List[str], max_n: int) -> List[Dict[str, Any]]:
    """Keep top reranked chunks; apply domain filter only when gate is enabled and terms exist."""
    if not ranked:
        return []
    if not required_terms:
        return ranked[:max_n]

    matched = [
        c
        for c in ranked
        if _chunk_matches_domain_requirements(_norm_text(c.get("text") or ""), required_terms)
    ]

    logger.debug(
        "domain_gate.filter required=%s ranked=%d passed=%d dropped=%d",
        required_terms,
        len(ranked),
        len(matched),
        len(ranked) - len(matched),
    )
    if matched:
        return matched[:max_n]

    # Gate eliminated ALL candidates.  Log details to aid debugging.
    logger.warning(
        "domain_gate.all_dropped required=%s — top-5 dropped snippets: %s",
        required_terms,
        [(c.get("document_id"), (c.get("text") or "")[:60]) for c in ranked[:5]],
    )
    return []


def hybrid_retrieve_for_qa(
    vector_store,
    question: str,
    course_id: Optional[str],
    lecture_id: Optional[str],
    *,
    return_scores: bool = False,
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Returns (chunks_for_context_and_sources, should_abstain, abstain_reason_or_empty).

    Pass return_scores=True to keep _rerank_score / _lex / _dist on each chunk
    (useful for the /debug/retrieval endpoint; callers must strip before prompting).
    """
    q = _norm_text(question)
    retrieval_plan = _build_retrieval_queries(q)
    retrieval_queries = retrieval_plan["queries"]
    tokens_list = []
    for query in retrieval_queries:
        tokens_list.extend(_tokenize_query(query))
    tokens_set = set(tokens_list)

    phrases_in_q: List[str] = []
    for ph in DOMAIN_TERMS_HE:
        if any(ph in query for query in retrieval_queries):
            phrases_in_q.append(ph)
    for syn, canon in QUESTION_PHRASE_TO_CANONICAL.items():
        if any(syn in query for query in retrieval_queries):
            phrases_in_q.append(syn)
            if canon not in phrases_in_q:
                phrases_in_q.append(canon)

    required_domain = domain_terms_in_question(q)
    logger.info(
        "retrieval.query_plan language=%s definition_mode=%s acronym_mode=%s key_term=%r expanded_queries=%s",
        retrieval_plan["language"],
        retrieval_plan["definition_mode"],
        retrieval_plan["is_acronym"],
        retrieval_plan["key_term"],
        retrieval_queries,
    )

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

        # Warn when we hit the fetch ceiling — retrieval may be incomplete.
        if raw_fetched >= _LEX_MAX_FETCH:
            logger.warning(
                "retrieval.lex_fetch_at_limit course_id=%s lecture_id=%s fetched=%d limit=%d "
                "— lexical search may miss chunks beyond this limit",
                course_id,
                lecture_id,
                raw_fetched,
                _LEX_MAX_FETCH,
            )
        else:
            logger.debug(
                "retrieval.lex_fetch course_id=%s lecture_id=%s fetched=%d limit=%d",
                course_id,
                lecture_id,
                raw_fetched,
                _LEX_MAX_FETCH,
            )

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

    logger.debug(
        "retrieval.lex_candidates course_id=%s lex_enabled=%s raw_fetched=%d scored=%d",
        course_id,
        lex_enabled,
        raw_fetched,
        len(lex_chunks),
    )

    try:
        vec_chunks = []
        for idx, query_text in enumerate(retrieval_queries):
            vec_chunks.extend(
                vector_store.search_with_distances(
                    query=query_text,
                    course_id=course_id,
                    lecture_id=lecture_id,
                    top_k=_VECTOR_CANDIDATES if idx == 0 else max(8, _VECTOR_CANDIDATES // 2),
                )
            )
    except Exception as exc:
        logger.warning("retrieval.vec_search_failed course_id=%s error=%s", course_id, exc)
        vec_chunks = []

    logger.debug(
        "retrieval.vec_candidates count=%d top_dist=%.4f",
        len(vec_chunks),
        vec_chunks[0].get("_distance", -1) if vec_chunks else -1,
    )

    ranked = merge_and_rerank(
        lex_chunks,
        vec_chunks,
        tokens_set,
        phrases_in_q,
        domain_query=bool(required_domain),
        expected_terms=retrieval_plan["expected_terms"],
    )

    if not ranked:
        logger.info(
            "retrieval.abstain reason=no_candidates course_id=%s lecture_id=%s "
            "lex_enabled=%s raw_fetched=%d lex_candidates=%d vec_candidates=%d",
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
            "retrieval.abstain reason=domain_gate course_id=%s lecture_id=%s "
            "lex_enabled=%s raw_fetched=%d ranked=%d domain_required=%s",
            course_id,
            lecture_id,
            lex_enabled,
            raw_fetched,
            len(ranked),
            required_domain,
        )
        return [], True, "domain_gate"

    if not top:
        logger.info(
            "retrieval.abstain reason=no_candidates_after_filter course_id=%s lecture_id=%s",
            course_id,
            lecture_id,
        )
        return [], True, "no_candidates"

    if return_scores:
        # Caller wants raw scoring data (e.g. debug endpoint); return as-is.
        logger.info(
            "retrieval.final course_id=%s selected=%d abstain=False (scores retained)",
            course_id,
            len(top),
        )
        return top, False, ""

    # Strip internal scoring keys before returning to QA agent / sources pipeline.
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
        "retrieval.final course_id=%s lecture_id=%s lex_enabled=%s "
        "raw_fetched=%d lex_candidates=%d vec_candidates=%d ranked=%d selected=%s",
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
