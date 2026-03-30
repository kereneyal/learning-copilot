import os
import json
import re
from typing import Any, Dict, List, Tuple

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except Exception:
    OLLAMA_AVAILABLE = False


PERSON_PATTERNS = [
    r'ד"ר\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
    r'עו"ד\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
    r'רו"ח\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
    r'פרופ[\'"]?\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
    r'השופט(?:\s+בדימוס)?[,]?\s*ד"ר\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
    r'מר\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
    r'גב[\'"]?\s+[א-ת"\']+(?:\s+[א-ת"\']+){0,4}',
]

TIME_RANGE_RE = r"\d{1,2}:\d{2}-\d{1,2}:\d{2}"
DATE_RE = r"\d{1,2}\.\d{1,2}\.\d{2,4}"


class SyllabusParserAgent:
    def __init__(self):
        self.client = None
        if OPENAI_AVAILABLE:
            try:
                self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            except Exception:
                self.client = None

    def parse(self, text: str) -> Dict[str, Any]:
        clean_text = self._normalize_text(text)
        warnings = []

        if self.client:
            try:
                parsed = self._parse_openai(clean_text)
                parsed["parser_used"] = "openai"
                parsed["parser_warnings"] = warnings
                return parsed
            except Exception as e:
                warnings.append(f"OpenAI parser failed: {e}")

        if OLLAMA_AVAILABLE:
            try:
                parsed = self._parse_ollama(clean_text)
                parsed["parser_used"] = "ollama"
                parsed["parser_warnings"] = warnings
                return parsed
            except Exception as e:
                warnings.append(f"Ollama parser failed: {e}")

        parsed = self._parse_directors_program(clean_text)
        parsed["parser_used"] = "regex_fallback"
        parsed["parser_warnings"] = warnings
        return parsed

    def _parse_openai(self, text: str) -> Dict[str, Any]:
        prompt = f"""
Extract structured course information from this syllabus.

Return ONLY valid JSON in this exact structure:

{{
  "course_name": "",
  "institution": "",
  "semester": "",
  "language": "",
  "lecturers": [
    {{
      "full_name": "",
      "bio": ""
    }}
  ],
  "lectures": [
    {{
      "title": "",
      "lecture_date": "",
      "lecturer_name": "",
      "notes": ""
    }}
  ]
}}

Rules:
- Hebrew output if the syllabus is Hebrew.
- One lecture = one meeting.
- Put all subtopics of the meeting into notes.
- Do not wrap in markdown.

SYLLABUS:
{text[:12000]}
"""
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""
        parsed = json.loads(self._extract_json_block(content))
        return self._post_process(parsed)

    def _parse_ollama(self, text: str) -> Dict[str, Any]:
        prompt = f"""
Extract structured course information from this syllabus.

Return ONLY JSON in this exact structure:

{{
  "course_name": "",
  "institution": "",
  "semester": "",
  "language": "",
  "lecturers": [
    {{
      "full_name": "",
      "bio": ""
    }}
  ],
  "lectures": [
    {{
      "title": "",
      "lecture_date": "",
      "lecturer_name": "",
      "notes": ""
    }}
  ]
}}

Important:
- One lecture = one meeting.
- Put all subtopics into notes.

SYLLABUS:
{text[:12000]}
"""
        response = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response["message"]["content"]
        try:
            parsed = json.loads(self._extract_json_block(content))
            return self._post_process(parsed)
        except Exception:
            return self._parse_directors_program(text)

    def _parse_directors_program(self, text: str) -> Dict[str, Any]:
        course_name = self._extract_course_name(text)
        institution = self._extract_institution(text)
        semester = self._extract_semester(text)
        language = self._detect_language(text)

        meeting_blocks = self._extract_meeting_blocks(text)
        lectures = []

        for meeting_num, block in meeting_blocks:
            lecture = self._parse_meeting_block(meeting_num, block)
            if lecture:
                lectures.append(lecture)

        lecturers = self._extract_lecturers_from_lectures(lectures)

        return self._post_process({
            "course_name": course_name,
            "institution": institution,
            "semester": semester,
            "language": language,
            "lecturers": lecturers,
            "lectures": lectures,
        })

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"(?<!\s)(מפגש\s*\d+)", r" \1", text)
        return text.strip()

    def _extract_json_block(self, content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return content[start:end + 1]
        return content

    def _detect_language(self, text: str) -> str:
        hebrew_chars = len(re.findall(r"[\u0590-\u05FF]", text))
        latin_chars = len(re.findall(r"[A-Za-z]", text))
        if hebrew_chars > latin_chars:
            return "he"
        if latin_chars > 0:
            return "en"
        return "unknown"

    def _extract_course_name(self, text: str) -> str:
        m = re.search(r"תכנית מתקדמת להסמכת דירקטורים ונושאי משרה בכירה", text)
        if m:
            return m.group(0)

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines[:20]:
            if "תכנית" in line or "תוכנית" in line or "קורס" in line:
                return line
        return "Course"

    def _extract_institution(self, text: str) -> str:
        lower = text.lower()
        if "lahav" in lower or "lahav.ac.il" in lower:
            return "Lahav"
        if "אוניברסיטת תל אביב" in text:
            return "אוניברסיטת תל אביב"
        return ""

    def _extract_semester(self, text: str) -> str:
        if "2026" in text:
            return "2026"
        m = re.search(r"202[0-9]", text)
        return m.group(0) if m else ""

    def _extract_meeting_blocks(self, text: str) -> List[Tuple[int, str]]:
        pattern = r"(מפגש\s*\d+.*?)(?=מפגש\s*\d+|בחינת בית|$)"
        raw_blocks = re.findall(pattern, text, flags=re.S)
        blocks = []

        for block in raw_blocks:
            m = re.search(r"מפגש\s*(\d+)", block)
            if not m:
                continue
            blocks.append((int(m.group(1)), block.strip()))

        blocks.sort(key=lambda x: x[0])
        return blocks

    def _parse_meeting_block(self, meeting_num: int, block: str) -> Dict[str, str]:
        date_match = re.search(DATE_RE, block)
        lecture_date = date_match.group(0) if date_match else ""

        # split to manageable lines
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        lines = [
            l for l in lines
            if not re.search(rf"^מפגש\s*{meeting_num}$", l)
            and not re.search(DATE_RE, l)
            and l != "*יום ראשון"
        ]

        # remove pure time-only lines
        lines = [l for l in lines if not re.fullmatch(TIME_RANGE_RE, l)]

        # sometimes time appears inline with text; remove times but keep text
        cleaned = []
        for line in lines:
            line = re.sub(TIME_RANGE_RE, "", line).strip(" -–—")
            line = re.sub(r"\s{2,}", " ", line).strip()
            if line:
                cleaned.append(line)

        topics = []
        people = []

        for line in cleaned:
            found_people = self._find_people(line)
            if found_people:
                people.extend(found_people)
                topic = line
                for p in found_people:
                    topic = topic.replace(p, "").strip(" -–—,")
                topic = re.sub(r"\s{2,}", " ", topic).strip()
                if topic:
                    topics.append(topic)
            else:
                topics.append(line)

        topics = self._unique_preserve_order([t for t in topics if self._is_meaningful_topic(t)])
        people = self._unique_preserve_order([p for p in people if p])

        title = topics[0] if topics else f"מפגש {meeting_num}"
        notes = " | ".join(topics)
        lecturer_name = ", ".join(people)

        return {
            "title": title,
            "lecture_date": lecture_date,
            "lecturer_name": lecturer_name,
            "notes": notes,
        }

    def _find_people(self, text: str) -> List[str]:
        results = []
        for pattern in PERSON_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                if isinstance(m, tuple):
                    m = " ".join([x for x in m if x])
                results.append(m.strip())
        return self._unique_preserve_order(results)

    def _is_meaningful_topic(self, text: str) -> bool:
        if not text or len(text) < 2:
            return False
        if re.fullmatch(r"[•\-\*$begin:math:text$$end:math:text$]+", text):
            return False
        if text in {"מרצה", "נושא", "תאריך", "שעות"}:
            return False
        return True

    def _extract_lecturers_from_lectures(self, lectures: List[Dict[str, str]]) -> List[Dict[str, str]]:
        names = []
        for lecture in lectures:
            lecturer_field = (lecture.get("lecturer_name") or "").strip()
            if not lecturer_field:
                continue
            for part in lecturer_field.split(","):
                part = part.strip()
                if part:
                    names.append(part)

        names = self._unique_preserve_order(names)
        return [{"full_name": n, "bio": ""} for n in names]

    def _unique_preserve_order(self, items: List[str]) -> List[str]:
        seen = set()
        out = []
        for item in items:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item.strip())
        return out

    def _post_process(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        parsed = parsed or {}

        lecturers = parsed.get("lecturers") or []
        lectures = parsed.get("lectures") or []

        clean_lecturers = []
        seen_lecturers = set()

        for lecturer in lecturers:
            if not isinstance(lecturer, dict):
                continue
            full_name = (lecturer.get("full_name") or "").strip()
            bio = (lecturer.get("bio") or "").strip()
            if not full_name:
                continue
            key = full_name.lower()
            if key in seen_lecturers:
                continue
            seen_lecturers.add(key)
            clean_lecturers.append({
                "full_name": full_name,
                "bio": bio,
            })

        clean_lectures = []
        for lecture in lectures:
            if not isinstance(lecture, dict):
                continue
            title = (lecture.get("title") or "").strip()
            lecture_date = (lecture.get("lecture_date") or "").strip()
            lecturer_name = (lecture.get("lecturer_name") or "").strip()
            notes = (lecture.get("notes") or "").strip()

            if not title and not notes and not lecture_date:
                continue

            clean_lectures.append({
                "title": title or "מפגש",
                "lecture_date": lecture_date,
                "lecturer_name": lecturer_name,
                "notes": notes,
            })

        if not clean_lecturers:
            clean_lecturers = self._extract_lecturers_from_lectures(clean_lectures)

        return {
            "course_name": (parsed.get("course_name") or "Course").strip(),
            "institution": (parsed.get("institution") or "").strip(),
            "semester": (parsed.get("semester") or "").strip(),
            "language": (parsed.get("language") or "unknown").strip(),
            "lecturers": clean_lecturers,
            "lectures": clean_lectures,
        }
