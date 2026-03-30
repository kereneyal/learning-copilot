type Source = {
  course_id?: string
  course_name?: string
  lecture_id?: string
  lecture_title?: string
  document_id?: string
  document_name?: string
  snippet?: string
  chunk_index?: number
}

export default function SourcePanel({ sources }: { sources: Source[] }) {
  return (
    <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-4 text-lg font-semibold">מקורות</h3>

      {sources.length === 0 ? (
        <p className="text-sm text-slate-500">כאן יוצגו המקורות של התשובה האחרונה.</p>
      ) : (
        <div className="space-y-3">
          {sources.map((s, idx) => (
            <div key={idx} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
              <div><strong>קורס:</strong> {s.course_name || s.course_id || "לא ידוע"}</div>
              <div><strong>הרצאה:</strong> {s.lecture_title || s.lecture_id || "לא ידוע"}</div>
              <div><strong>מסמך:</strong> {s.document_name || s.document_id || "לא ידוע"}</div>
              {typeof s.chunk_index === "number" && (
                <div><strong>Chunk:</strong> {s.chunk_index}</div>
              )}
              {s.snippet && (
                <div className="mt-2 rounded-lg bg-white p-2 text-slate-600">
                  {s.snippet}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
