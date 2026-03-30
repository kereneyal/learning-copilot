#!/bin/bash

echo "Installing robust syllabus parser..."

AGENT_FILE="app/agents/syllabus_parser_agent.py"

cat > $AGENT_FILE << 'EOF'
import os
import json
import re

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except:
    OPENAI_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except:
    OLLAMA_AVAILABLE = False


class SyllabusParserAgent:

    def __init__(self):
        if OPENAI_AVAILABLE:
            try:
                self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            except:
                self.client = None
        else:
            self.client = None


    def parse(self, text):

        if self.client:
            try:
                return self._parse_openai(text)
            except Exception as e:
                print("OpenAI parser failed:", e)

        if OLLAMA_AVAILABLE:
            try:
                return self._parse_ollama(text)
            except Exception as e:
                print("Ollama parser failed:", e)

        return self._parse_basic(text)


    def _parse_openai(self, text):

        prompt = f"""
Extract structured course information from this syllabus.

Return JSON with this structure:

{{
  "course_name": "",
  "institution": "",
  "semester": "",
  "language": "",
  "lecturers": [
    {{ "full_name": "", "bio": "" }}
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

SYLLABUS:
{text[:8000]}
"""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0
        )

        content = response.choices[0].message.content

        return json.loads(content)


    def _parse_ollama(self, text):

        prompt = f"""
Extract course structure from this syllabus.

Return JSON:

course_name
institution
semester
language
lecturers[]
lectures[]

SYLLABUS:
{text[:8000]}
"""

        response = ollama.chat(
            model="llama3",
            messages=[{"role":"user","content":prompt}]
        )

        content = response["message"]["content"]

        try:
            return json.loads(content)
        except:
            return self._parse_basic(text)


    def _parse_basic(self, text):

        lines = text.split("\n")

        course_name = lines[0] if lines else "Course"

        lectures = []

        for line in lines:
            if re.search(r"lecture|week|topic", line.lower()):
                lectures.append({
                    "title": line.strip(),
                    "lecture_date": "",
                    "lecturer_name": "",
                    "notes": ""
                })

        return {
            "course_name": course_name,
            "institution": "",
            "semester": "",
            "language": "unknown",
            "lecturers": [],
            "lectures": lectures[:20]
        }

EOF

echo "Parser installed successfully."
echo "Restart backend."
