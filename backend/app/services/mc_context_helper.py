"""
Multiple-choice only: reorder retrieved chunks for lexical alignment with stem + options
and lightly penalize chunks that introduce digits absent from the question/options blob.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_TOKEN = re.compile(r"[\w\u0590-\u05FF]{2,}")


def _mc_query_blob(mc_parsed: Dict[str, Any]) -> str:
    stem = mc_parsed.get("stem") or ""
    opts = mc_parsed.get("options") or []
    parts = [stem]
    for o in opts:
        parts.append(f"{o.get('letter', '')}. {o.get('text', '')}")
    return "\n".join(p for p in parts if p).strip()


def _overlap_score(blob: str, chunk_text: str) -> float:
    words = {w.lower() for w in _TOKEN.findall(blob)}
    if not words:
        return 0.0
    low = chunk_text.lower()
    return float(sum(1 for w in words if w in low))


def order_chunks_for_mc(chunks: List[Dict[str, Any]], mc_parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not chunks or not mc_parsed:
        return chunks
    blob = _mc_query_blob(mc_parsed)
    if not blob:
        return chunks
    allowed_nums = set(_NUM.findall(blob))
    scored: List[tuple[float, Dict[str, Any]]] = []
    for c in chunks:
        t = c.get("text") or ""
        s = _overlap_score(blob, t)
        cnums = set(_NUM.findall(t))
        extra = cnums - allowed_nums
        if extra and allowed_nums:
            s -= 3.0 * len(extra)
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored]
