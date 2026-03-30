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
import sys

path = Path("app/knowledge/page.tsx")
text = path.read_text()

def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)

anchor = '{activeTab === "documents" && ('
if anchor not in text:
    fail('Could not find documents tab anchor')

insert = '''{activeTab === "documents" && (
        <>
          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">העלאת מסמכים להרצאה</h3>
              <div className="text-sm text-slate-500">
                {selectedCourse ? `קורס נבחר: ${selectedCourse.name}` : "בחר קורס לפני העלאה"}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
              <select
                className="rounded-xl border px-3 py-2"
                value={selectedCourseId}
                onChange={(e) => setSelectedCourseId(e.target.value)}
              >
                <option value="">בחר קורס</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.name}
                  </option>
                ))}
              </select>

              <select
                className="rounded-xl border px-3 py-2"
                value={uploadForm.lecture_id}
                onChange={(e) => {
                  const value = e.target.value
                  setUploadForm((p) => ({ ...p, lecture_id: value }))
                  if (value) setSelectedLectureId(value)
                }}
              >
                <option value="">בחר הרצאה לשיוך</option>
                {lectures.map((lecture) => (
                  <option key={lecture.id} value={lecture.id}>
                    {lecture.title}
                  </option>
                ))}
              </select>

              <input
                className="rounded-xl border px-3 py-2"
                placeholder="נושא"
                value={uploadForm.topic}
                onChange={(e) => setUploadForm((p) => ({ ...p, topic: e.target.value }))}
              />

              <select
                className="rounded-xl border px-3 py-2"
                value={uploadForm.source_type}
                onChange={(e) => setUploadForm((p) => ({ ...p, source_type: e.target.value }))}
              >
                <option value="slides">מצגת</option>
                <option value="summary">סיכום</option>
                <option value="notes">הערות</option>
                <option value="article">מאמר</option>
                <option value="syllabus">סילבוס</option>
                <option value="audio">אודיו</option>
                <option value="video">וידאו</option>
              </select>

              <input
                className="rounded-xl border px-3 py-2"
                type="file"
                multiple
                onChange={(e) =>
                  setUploadForm((p) => ({
                    ...p,
                    files: e.target.files ? Array.from(e.target.files) : [],
                  }))
                }
              />
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              {uploadForm.files.length > 0 && (
                <div className="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-600">
                  נבחרו {uploadForm.files.length} קבצים
                </div>
              )}

              <button
                onClick={uploadFilesBatch}
                disabled={uploadingBatch}
                className="rounded-xl bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-50"
              >
                {uploadingBatch ? "מעלה..." : "העלה מסמכים להרצאה"}
              </button>
            </div>

            {uploadingBatch && uploadProgress > 0 && (
              <div className="mt-4 rounded-xl bg-slate-50 p-3">
                <div className="mb-2 text-sm text-slate-600">התקדמות העלאה</div>
                <div className="h-3 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <div className="mt-2 text-xs text-slate-500">{uploadProgress}%</div>
              </div>
            )}
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">'''

text = text.replace(anchor, insert, 1)

old_end = '''        </section>
      )}'''
new_end = '''        </section>
        </>
      )}'''

if old_end not in text:
    fail('Could not find documents section closing block')

text = text.replace(old_end, new_end, 1)

path.write_text(text)
print("Patched documents upload panel successfully")
PY

echo "Done."
echo "Now run:"
echo "npm run dev"
