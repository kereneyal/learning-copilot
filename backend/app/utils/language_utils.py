def detect_text_language(text: str) -> str:
    if not text:
        return "en"

    hebrew_chars = sum(1 for ch in text if '\u0590' <= ch <= '\u05FF')
    english_chars = sum(1 for ch in text if ('a' <= ch.lower() <= 'z'))

    if hebrew_chars > english_chars:
        return "he"
    return "en"
