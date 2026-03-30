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

# 1) add processingStats memo before filteredDocuments
anchor = '  const filteredDocuments = useMemo(() => {\n'
block = '''  const processingStats = useMemo(() => {
    const safeDocuments = Array.isArray(documents) ? documents : []

    return {
      processing: safeDocuments.filter((d) => d.processing_status === "processing").length,
      failed: safeDocuments.filter((d) => d.processing_status === "failed").length,
      noSummary: safeDocuments.filter(
        (d: any) => (d.processing_status || "ready") === "ready" && !d.has_summary
      ).length,
      noRawText: safeDocuments.filter(
        (d: any) => (d.processing_status || "ready") === "ready" && !d.raw_text_length
      ).length,
    }
  }, [documents])

'''
if 'const processingStats = useMemo(() => {' not in text:
    if anchor not in text:
        fail("Could not find filteredDocuments anchor")
    text = text.replace(anchor, block + anchor, 1)

# 2) replace joint documents/processing block with separate documents block
old_pattern = r'\{\(activeTab === "documents" \|\| activeTab === "processing"\) && \(\n.*?\n      \)\}'
new_documents_block = r'''{activeTab === "documents" && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <h3 className="text-lg font-semibold">מסמכים</h3>
            <div className="text-sm text-slate-500">
              {selectedLecture
                ? `תצוגה עבור הרצאה: ${selectedLecture.title}`
                : selectedCourse
                ? `תצוגה עבור קורס: ${selectedCourse.name}`
                : "בחר קורס או הרצאה"}
            </div>
          </div>

          <div className="mb-3 flex flex-wrap gap-2">
            <button onClick={() => setQuickFilter("all")} className={`rounded-xl px-3 py-2 text-sm ${quickFilter === "all" ? "bg-slate-900 text-white" : "bg-slate-100"}`}>הכול</button>
            <button onClick={() => setQuickFilter("failed")} className={`rounded-xl px-3 py-2 text-sm ${quickFilter === "failed" ? "bg-red-600 text-white" : "bg-red-100 text-red-700"}`}>רק נכשלו</button>
            <button onClick={() => setQuickFilter("processing")} className={`rounded-xl px-3 py-2 text-sm ${quickFilter === "processing" ? "bg-amber-600 text-white" : "bg-amber-100 text-amber-700"}`}>רק בעיבוד</button>
            <button onClick={() => setQuickFilter("no_summary")} className={`rounded-xl px-3 py-2 text-sm ${quickFilter === "no_summary" ? "bg-indigo-600 text-white" : "bg-indigo-100 text-indigo-700"}`}>בלי summary</button>
            <button onClick={() => setQuickFilter("selected_lecture")} className={`rounded-xl px-3 py-2 text-sm ${quickFilter === "selected_lecture" ? "bg-purple-600 text-white" : "bg-purple-100 text-purple-700"}`}>רק ההרצאה הנבחרת</button>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-6">
            <input className="rounded-xl border px-3 py-2" placeholder="חפש מסמך, נושא או הרצאה" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
            <select className="rounded-xl border px-3 py-2" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">כל הסטטוסים</option>
              <option value="ready">מוכן</option>
              <option value="processing">בעיבוד</option>
              <option value="failed">נכשל</option>
            </select>
            <select className="rounded-xl border px-3 py-2" value={languageFilter} onChange={(e) => setLanguageFilter(e.target.value)}>
              <option value="all">כל השפות</option>
              <option value="he">עברית</option>
              <option value="en">אנגלית</option>
              <option value="unknown">לא זוהתה</option>
            </select>
            <select className="rounded-xl border px-3 py-2" value={sourceTypeFilter} onChange={(e) => setSourceTypeFilter(e.target.value)}>
              <option value="all">כל סוגי המקור</option>
              <option value="slides">מצגת</option>
              <option value="summary">סיכום</option>
              <option value="notes">הערות</option>
              <option value="article">מאמר</option>
              <option value="syllabus">סילבוס</option>
              <option value="audio">אודיו</option>
              <option value="video">וידאו</option>
            </select>
            <select className="rounded-xl border px-3 py-2" value={lectureFilter} onChange={(e) => setLectureFilter(e.target.value)}>
              <option value="all">כל ההרצאות</option>
              {lectures.map((lecture) => (
                <option key={lecture.id} value={lecture.id}>
                  {lecture.title}
                </option>
              ))}
            </select>
            <select className="rounded-xl border px-3 py-2" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="file_name">מיין לפי שם</option>
              <option value="status">מיין לפי סטטוס</option>
              <option value="language">מיין לפי שפה</option>
            </select>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <input
              className="rounded-xl border px-3 py-2 text-sm"
              placeholder="שם לתצוגה שמורה"
              value={newSavedViewName}
              onChange={(e) => setNewSavedViewName(e.target.value)}
            />
            <button onClick={saveCurrentView} className="rounded-xl bg-slate-900 px-4 py-2 text-sm text-white">
              שמור תצוגה
            </button>
            {savedViews.map((view) => (
              <div key={view.name} className="flex items-center gap-1 rounded-xl bg-slate-100 px-2 py-1">
                <button onClick={() => applySavedView(view)} className="text-sm">
                  {view.name}
                </button>
                <button onClick={() => deleteSavedView(view.name)} className="text-xs text-red-600">
                  ✕
                </button>
              </div>
            ))}
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <button onClick={toggleSelectAllVisible} className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium">
              בחר / בטל בחירה של העמוד
            </button>
            <button onClick={bulkRetryFailed} className="rounded-xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-700">
              נסה שוב לנכשלים המסומנים
            </button>
            <button onClick={bulkDeleteDocuments} className="rounded-xl bg-red-100 px-4 py-2 text-sm font-medium text-red-700">
              מחק מסומנים
            </button>
            <select
              className="rounded-xl border px-3 py-2 text-sm"
              value={bulkRelinkLectureId}
              onChange={(e) => setBulkRelinkLectureId(e.target.value)}
            >
              <option value="">בחר הרצאה יעד לשיוך מחדש</option>
              {lectures.map((lecture) => (
                <option key={lecture.id} value={lecture.id}>
                  {lecture.title}
                </option>
              ))}
            </select>
            <button onClick={bulkRelinkDocuments} className="rounded-xl bg-blue-100 px-4 py-2 text-sm font-medium text-blue-700">
              שיוך מחדש להרצאה
            </button>
            <button
              onClick={() => {
                setSearchTerm("")
                setStatusFilter("all")
                setLanguageFilter("all")
                setSourceTypeFilter("all")
                setLectureFilter("all")
                setSortBy("file_name")
                setQuickFilter("all")
              }}
              className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium"
            >
              נקה מסננים
            </button>
          </div>

          {filteredDocuments.length === 0 ? (
            <EmptyState title="אין מסמכים להצגה" description="שנה מסננים או העלה מסמכים חדשים." />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full border-separate border-spacing-y-2 text-sm">
                  <thead>
                    <tr className="text-right text-slate-500">
                      <th className="px-3 py-2"></th>
                      <th className="px-3 py-2">שם קובץ</th>
                      <th className="px-3 py-2">הרצאה</th>
                      <th className="px-3 py-2">סוג מקור</th>
                      <th className="px-3 py-2">שפה</th>
                      <th className="px-3 py-2">סטטוס</th>
                      <th className="px-3 py-2">פעולות</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedDocuments.map((doc) => (
                      <tr key={doc.id} className="bg-slate-50">
                        <td className="rounded-r-2xl px-3 py-3">
                          <input
                            type="checkbox"
                            checked={selectedDocumentIds.includes(doc.id)}
                            onChange={() => toggleDocumentSelection(doc.id)}
                          />
                        </td>
                        <td className="px-3 py-3 font-medium">{doc.file_name}</td>
                        <td className="px-3 py-3">{doc.lecture_title || "ללא הרצאה"}</td>
                        <td className="px-3 py-3">{doc.source_type || "unknown"}</td>
                        <td className="px-3 py-3">{doc.language || "unknown"}</td>
                        <td className="px-3 py-3">{renderStatusBadge(doc.processing_status)}</td>
                        <td className="rounded-l-2xl px-3 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button onClick={() => fetchDocumentDetails(doc.id)} className="rounded-lg bg-blue-100 px-3 py-1 text-blue-700">
                              פרטי עיבוד
                            </button>
                            <button onClick={() => retryDocumentProcessing(doc.id)} className="rounded-lg bg-amber-100 px-3 py-1 text-amber-700">
                              נסה שוב
                            </button>
                            <button onClick={() => deleteDocument(doc.id)} className="rounded-lg bg-red-100 px-3 py-1 text-red-700">
                              מחק
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 flex items-center justify-between">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="rounded-xl bg-slate-100 px-4 py-2 disabled:opacity-50"
                >
                  הקודם
                </button>
                <div className="text-sm text-slate-500">
                  עמוד {currentPage} מתוך {totalPages}
                </div>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="rounded-xl bg-slate-100 px-4 py-2 disabled:opacity-50"
                >
                  הבא
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {activeTab === "processing" && (
        <section className="space-y-5">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-2xl border bg-white p-4 shadow-sm">
              <div className="text-sm text-slate-500">בעיבוד</div>
              <div className="mt-1 text-2xl font-semibold text-amber-700">{processingStats.processing}</div>
            </div>
            <div className="rounded-2xl border bg-white p-4 shadow-sm">
              <div className="text-sm text-slate-500">נכשלו</div>
              <div className="mt-1 text-2xl font-semibold text-red-700">{processingStats.failed}</div>
            </div>
            <div className="rounded-2xl border bg-white p-4 shadow-sm">
              <div className="text-sm text-slate-500">בלי summary</div>
              <div className="mt-1 text-2xl font-semibold text-indigo-700">{processingStats.noSummary}</div>
            </div>
            <div className="rounded-2xl border bg-white p-4 shadow-sm">
              <div className="text-sm text-slate-500">בלי raw text</div>
              <div className="mt-1 text-2xl font-semibold text-slate-700">{processingStats.noRawText}</div>
            </div>
          </div>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <h3 className="text-lg font-semibold">בקרת עיבוד</h3>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    setStatusFilter("processing")
                    setSearchTerm("")
                  }}
                  className="rounded-xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-700"
                >
                  הצג בעיבוד
                </button>
                <button
                  onClick={() => {
                    setStatusFilter("failed")
                    setSearchTerm("")
                  }}
                  className="rounded-xl bg-red-100 px-4 py-2 text-sm font-medium text-red-700"
                >
                  הצג נכשלים
                </button>
                <button
                  onClick={() => {
                    setStatusFilter("all")
                    setSearchTerm("")
                  }}
                  className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium"
                >
                  איפוס
                </button>
              </div>
            </div>

            <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-4">
              <input
                className="rounded-xl border px-3 py-2"
                placeholder="חפש קובץ"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <select className="rounded-xl border px-3 py-2" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="all">כל הסטטוסים</option>
                <option value="processing">בעיבוד</option>
                <option value="failed">נכשל</option>
                <option value="ready">מוכן</option>
              </select>
              <select className="rounded-xl border px-3 py-2" value={sourceTypeFilter} onChange={(e) => setSourceTypeFilter(e.target.value)}>
                <option value="all">כל סוגי המקור</option>
                <option value="slides">מצגת</option>
                <option value="summary">סיכום</option>
                <option value="notes">הערות</option>
                <option value="article">מאמר</option>
                <option value="syllabus">סילבוס</option>
                <option value="audio">אודיו</option>
                <option value="video">וידאו</option>
              </select>
              <select className="rounded-xl border px-3 py-2" value={lectureFilter} onChange={(e) => setLectureFilter(e.target.value)}>
                <option value="all">כל ההרצאות</option>
                {lectures.map((lecture) => (
                  <option key={lecture.id} value={lecture.id}>
                    {lecture.title}
                  </option>
                ))}
              </select>
            </div>

            {filteredDocuments.length === 0 ? (
              <EmptyState title="אין פריטי עיבוד להצגה" description="אין כרגע מסמכים תואמים למסננים." />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full border-separate border-spacing-y-2 text-sm">
                  <thead>
                    <tr className="text-right text-slate-500">
                      <th className="px-3 py-2">שם קובץ</th>
                      <th className="px-3 py-2">סטטוס</th>
                      <th className="px-3 py-2">שגיאה אחרונה</th>
                      <th className="px-3 py-2">אורך טקסט</th>
                      <th className="px-3 py-2">summary</th>
                      <th className="px-3 py-2">פעולות</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredDocuments.map((doc: any) => (
                      <tr key={doc.id} className="bg-slate-50">
                        <td className="rounded-r-2xl px-3 py-3 font-medium">{doc.file_name}</td>
                        <td className="px-3 py-3">{renderStatusBadge(doc.processing_status)}</td>
                        <td className="px-3 py-3">
                          <div className="max-w-[260px] truncate text-xs text-red-700">
                            {doc.last_error || "-"}
                          </div>
                        </td>
                        <td className="px-3 py-3">{doc.raw_text_length || 0}</td>
                        <td className="px-3 py-3">
                          {(doc as any).has_summary ? "כן" : "לא"}
                        </td>
                        <td className="rounded-l-2xl px-3 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={() => fetchDocumentDetails(doc.id)}
                              className="rounded-lg bg-blue-100 px-3 py-1 text-blue-700"
                            >
                              פרטי עיבוד
                            </button>
                            <button
                              onClick={() => retryDocumentProcessing(doc.id)}
                              className="rounded-lg bg-amber-100 px-3 py-1 text-amber-700"
                            >
                              retry
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </section>
      )}'''

new_text, count = re.subn(old_pattern, new_documents_block, text, count=1, flags=re.S)
if count == 0:
    fail("Could not replace documents/processing combined block")

text = new_text
path.write_text(text)
print("Patched processing tab successfully")
PY

echo "Done."
echo "Now run:"
echo "npm run dev"
