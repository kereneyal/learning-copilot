#!/bin/bash

set -e

FILE="app/knowledge/page.tsx"

if [ ! -f "$FILE" ]; then
  echo "ERROR: $FILE not found"
  exit 1
fi

BACKUP="${FILE}.backup.$(date +%Y%m%d_%H%M%S)"
cp "$FILE" "$BACKUP"
echo "Backup created: $BACKUP"

python3 <<'PY'
from pathlib import Path
import re
import sys

path = Path("app/knowledge/page.tsx")
text = path.read_text()

def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)

# 1) add loading state if missing
anchor = '  const [studyOutput, setStudyOutput] = useState("")\n'
addition = '  const [studyLoading, setStudyLoading] = useState(false)\n'
if 'const [studyLoading, setStudyLoading] = useState(false)' not in text:
    if anchor not in text:
        fail("Could not find studyOutput state")
    text = text.replace(anchor, anchor + addition, 1)

# 2) replace generateStudyContent with backend-connected version
pattern = r'''  function generateStudyContent\(action: "summary" \| "flashcards" \| "quiz"\) \{
.*?
  \}
'''
replacement = '''  async function generateStudyContent(action: "summary" | "flashcards" | "quiz") {
    const safeDocuments = Array.isArray(documents) ? documents : []
    const selectedDoc = safeDocuments.find((d) => String(d.id) === String(studyDocId))

    if (!selectedDoc) {
      setStudyOutput("יש לבחור מסמך קודם.")
      return
    }

    const baseText =
      (selectedDoc as any).summary_text ||
      (selectedDoc as any).raw_text_preview ||
      (selectedDoc as any).topic ||
      ""

    if (!baseText || !String(baseText).trim()) {
      setStudyOutput("אין עדיין מספיק תוכן למסמך הזה. נסה מסמך אחר או ודא שעיבוד המסמך הסתיים.")
      return
    }

    try {
      setStudyLoading(true)
      setStudyOutput("טוען תוכן לימוד...")

      const res = await fetch(`${API_BASE}/ai/study`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: String(baseText),
          mode: action,
        }),
      })

      if (!res.ok) {
        throw new Error("AI study request failed")
      }

      const data = await res.json()

      if (action === "summary") {
        setStudyOutput(data.summary || "לא נוצר סיכום.")
        return
      }

      if (action === "flashcards") {
        const cards = Array.isArray(data.flashcards) ? data.flashcards : []
        if (cards.length === 0) {
          setStudyOutput("לא נוצרו Flashcards.")
          return
        }

        setStudyOutput(
          cards
            .map(
              (card: any, i: number) =>
                `כרטיס ${i + 1}:\\nשאלה: ${card.question || ""}\\nתשובה: ${card.answer || ""}`
            )
            .join("\\n\\n")
        )
        return
      }

      const quiz = Array.isArray(data.quiz) ? data.quiz : []
      if (quiz.length === 0) {
        setStudyOutput("לא נוצרו שאלות מבחן.")
        return
      }

      setStudyOutput(
        quiz
          .map(
            (item: any, i: number) =>
              `שאלה ${i + 1}:\\n${item.question || ""}\\nתשובה: ${item.answer || ""}`
          )
          .join("\\n\\n")
      )
    } catch (err) {
      console.error(err)
      setStudyOutput("שגיאה ביצירת תוכן לימוד באמצעות AI.")
    } finally {
      setStudyLoading(false)
    }
  }
'''
new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
if count == 0:
    fail("Could not replace generateStudyContent")
text = new_text

# 3) update button label in modal
old_button = '''                <button
                  onClick={() => generateStudyContent(studyAction)}
                  className="rounded-xl bg-indigo-600 px-4 py-2 text-white"
                >
                  צור תוכן לימוד
                </button>'''
new_button = '''                <button
                  onClick={() => generateStudyContent(studyAction)}
                  disabled={studyLoading}
                  className="rounded-xl bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
                >
                  {studyLoading ? "מייצר..." : "צור תוכן לימוד"}
                </button>'''
if old_button in text:
    text = text.replace(old_button, new_button, 1)

# 4) update output placeholder
old_output = '{studyOutput || "בחר מסמך ולחץ על \'צור תוכן לימוד\'."}'
new_output = '{studyOutput || "בחר מסמך, בחר סוג פלט ולחץ על יצירה."}'
if old_output in text:
    text = text.replace(old_output, new_output, 1)

path.write_text(text)
print("Patched app/knowledge/page.tsx successfully")
PY

echo "Done."
echo "Now run:"
echo "npm run dev"
