import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.course import Course


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\u0590-\u05FF]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def generate_aliases(course_name: str):
    normalized = normalize_text(course_name)
    aliases = {normalized}

    parts = normalized.split()
    if len(parts) > 1:
        aliases.add(" ".join(parts[:2]))
        aliases.add(parts[0])

    return {a for a in aliases if a}


def resolve_course_from_question(db: Session, question: str) -> Tuple[Optional[str], float]:
    normalized_question = normalize_text(question)
    if not normalized_question:
        return None, 0.0

    courses = db.query(Course).all()
    best_course_id = None
    best_score = 0.0

    for course in courses:
        aliases = generate_aliases(course.name or "")
        score = 0.0

        for alias in aliases:
            if alias and alias in normalized_question:
                score = max(score, min(1.0, len(alias) / max(len(normalized_question), 1) + 0.4))

        course_name_words = set(normalize_text(course.name or "").split())
        question_words = set(normalized_question.split())

        if course_name_words:
            overlap = len(course_name_words & question_words) / len(course_name_words)
            score = max(score, overlap)

        if score > best_score:
            best_score = score
            best_course_id = course.id

    if best_score >= 0.45:
        return best_course_id, best_score

    return None, best_score
