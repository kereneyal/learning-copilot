"""
Detect and parse multiple-choice questions from chat input.

Supported markers:
  Hebrew: א. ב. ג. … (line-based: any Hebrew letter; strict inline: א–ה)
  English: A. B. C. … (line-based: any Latin letter; strict inline: A–E)

Line-based: each option on its own line.
Strict inline: regex segments for typical exam labels (א–ה / A–E).
Broad inline fallback: start-of-string or whitespace before marker.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

OptionScript = Literal["hebrew", "latin"]

# Hebrew letter + dot + option text (full line)
_HEBREW_OPTION = re.compile(r"^\s*([א-ת])\s*\.\s*(.+?)\s*$")
# Single Latin letter + dot + option text (full line)
_LATIN_OPTION = re.compile(r"^\s*([A-Za-z])\s*\.\s*(.+?)\s*$")

# Strict inline: common MC labels only (per typical 4–5 option exams)
_INLINE_LATIN_STRICT = re.compile(
    r"(?is)(?:^|\s)([A-E])\.(?:\s*)(.*?)(?=(?:\s+[A-E]\.\s)|$)"
)
_INLINE_HEBREW_STRICT = re.compile(
    r"(?is)(?:^|\s)([אבגדה])\.(?:\s*)(.*?)(?=(?:\s+[אבגדה]\.\s)|$)"
)

# Broad inline: marker at start or after whitespace
_INLINE_LATIN_MARKER = re.compile(r"(?:^|(?<=\s))([A-Z])\.\s+")
_INLINE_HEBREW_MARKER = re.compile(r"(?:^|(?<=\s))([א-ת])\.\s+")
_INLINE_LATIN_MARKER_LOWER = re.compile(r"(?:^|(?<=\s))([a-z])\.\s+")


def _build_result(
    stem: str,
    script: OptionScript,
    options: List[Dict[str, str]],
) -> Dict[str, Any]:
    opts_lines = "\n".join(f"{o['letter']}. {o['text']}" for o in options)
    retrieval_query = f"{stem}\n{opts_lines}".strip() if stem else opts_lines
    return {
        "stem": stem,
        "option_script": script,
        "options": options,
        "retrieval_query": retrieval_query,
    }


def _try_parse_line_based(text: str) -> Optional[Dict[str, Any]]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()

    first_idx: Optional[int] = None
    script: Optional[OptionScript] = None

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        mh = _HEBREW_OPTION.match(s)
        ml = _LATIN_OPTION.match(s)
        if mh:
            script = "hebrew"
            first_idx = i
            break
        if ml:
            script = "latin"
            first_idx = i
            break

    if first_idx is None or script is None:
        return None

    stem_lines = [ln.strip() for ln in lines[:first_idx] if ln.strip()]
    stem = "\n".join(stem_lines).strip()

    pat = _HEBREW_OPTION if script == "hebrew" else _LATIN_OPTION
    options: List[Dict[str, str]] = []
    for line in lines[first_idx:]:
        s = line.strip()
        if not s:
            continue
        m = pat.match(s)
        if not m:
            break
        letter, body = m.group(1), m.group(2).strip()
        if script == "latin":
            letter = letter.upper()
        options.append({"letter": letter, "text": body})

    if len(options) < 2:
        return None

    return _build_result(stem, script, options)


def _options_from_inline_strict(
    text: str, matches: List[re.Match[str]], script: OptionScript
) -> Optional[List[Dict[str, str]]]:
    if len(matches) < 2:
        return None
    options: List[Dict[str, str]] = []
    for m in matches:
        letter_raw = m.group(1)
        letter = letter_raw.upper() if script == "latin" else letter_raw
        body = m.group(2).strip()
        if not body:
            return None
        options.append({"letter": letter, "text": body})
    return options


def _try_parse_inline_regex(text: str) -> Optional[Dict[str, Any]]:
    """Strict A–E / א–ה inline segments (single line or multiline)."""
    for script, pattern in (
        ("latin", _INLINE_LATIN_STRICT),
        ("hebrew", _INLINE_HEBREW_STRICT),
    ):
        matches = list(pattern.finditer(text))
        if len(matches) < 2:
            continue
        options = _options_from_inline_strict(text, matches, script)
        if not options:
            continue
        stem = text[: matches[0].start()].strip()
        logger.info(
            "multiple_choice_parser: inline regex strict (%s), options=%d stem_len=%d",
            script,
            len(options),
            len(stem),
        )
        return _build_result(stem, script, options)
    return None


def _options_from_inline_spans(
    text: str,
    matches: List[re.Match[str]],
    script: OptionScript,
) -> Optional[List[Dict[str, str]]]:
    if len(matches) < 2:
        return None

    options: List[Dict[str, str]] = []
    for i, m in enumerate(matches):
        raw_letter = m.group(1)
        letter = raw_letter.upper() if script == "latin" else raw_letter
        end_content = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end_content].strip()
        if not body:
            return None
        options.append({"letter": letter, "text": body})

    return options


def _try_parse_inline_broad(text: str) -> Optional[Dict[str, Any]]:
    latin_matches = list(_INLINE_LATIN_MARKER.finditer(text))
    if len(latin_matches) < 2:
        latin_matches = list(_INLINE_LATIN_MARKER_LOWER.finditer(text))

    if len(latin_matches) >= 2:
        options = _options_from_inline_spans(text, latin_matches, "latin")
        if options:
            stem = text[: latin_matches[0].start()].strip()
            logger.info(
                "multiple_choice_parser: inline broad latin, options=%d stem_len=%d",
                len(options),
                len(stem),
            )
            return _build_result(stem, "latin", options)

    hebrew_matches = list(_INLINE_HEBREW_MARKER.finditer(text))
    if len(hebrew_matches) >= 2:
        options = _options_from_inline_spans(text, hebrew_matches, "hebrew")
        if options:
            stem = text[: hebrew_matches[0].start()].strip()
            logger.info(
                "multiple_choice_parser: inline broad hebrew, options=%d stem_len=%d",
                len(options),
                len(stem),
            )
            return _build_result(stem, "hebrew", options)

    return None


def parse_multiple_choice(raw: str) -> Optional[Dict[str, Any]]:
    """
    If the text contains a stem followed by at least two labeled options in one script,
    return a structured dict; otherwise None (caller keeps normal QA).

    Returns:
        stem: question text before the first option
        option_script: "hebrew" | "latin"
        options: [{"letter": str, "text": str}, ...]
        retrieval_query: stem + options (for hybrid / embedding)
    """
    text = (raw or "").strip()
    if not text:
        return None

    line_result = _try_parse_line_based(text)
    if line_result is not None:
        return line_result

    regex_result = _try_parse_inline_regex(text)
    if regex_result is not None:
        return regex_result

    return _try_parse_inline_broad(text)
