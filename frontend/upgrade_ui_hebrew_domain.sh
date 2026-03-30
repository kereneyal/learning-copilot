#!/bin/bash

set -e

npm install react-markdown

cat > .env.local <<'EOF'
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
EOF

cat > app/page.tsx <<'EOF'
"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"

type Course = {
  id: string
  name: string
  institution?: string
  semester?: string
}

type Lecturer = {
  id: string
  full_name: string
  bio?: string
}

type Lecture = {
  id: string
  course_id: string
  lecturer_id: string
  lecturer_name?: string
  title: string
  lecture_date?: string
  notes?: string
}

type CourseDocument = {
  id: string
  course_id: string
  lecture_id?: string
  lecture_title?: string
  file_name: string
  file_type?: string
  language?: string
  topic?: string
  source_type?: string
  uploaded_at?: string
}

type Source = {
  document_id?: string
  chunk_index?: number
  course_id?: string
}

type Message = {
  role: "user" | "assistant"
  content: string
  intent?: string
  sources?: Source[]
}

export default function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [lecturers, setLecturers] = useState<Lecturer[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [documents, setDocuments] = useState<CourseDocument[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [error, setError] = useState("")
  const [sending, setSending] = useState(false)
  const [loadingCourses, setLoadingCourses] = useState(false)
  const [loadingLecturers, setLoadingLecturers] = useState(false)
  const [loadingLectures, setLoadingLectures] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [creatingCourse, setCreatingCourse] = useState(false)
  const [creatingLecturer, setCreatingLecturer] = useState(false)
  const [creatingLecture, setCreatingLecture] = useState(false)
  const [uploading, setUploading] = useState(false)

  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  const [newCourse, setNewCourse] = useState({
    name: "",
    institution: "",
    default_language: "en",
    semester: "",
    lecturer_name: "",
  })

  const [newLecturer, setNewLecturer] = useState({
    full_name: "",
    bio: "",
  })

  const [newLecture, setNewLecture] = useState({
    title: "",
    lecturer_id: "",
    lecture_date: "",
    notes: "",
  })

  const [uploadForm, setUploadForm] = useState({
    topic: "",
    source_type: "slides",
    file: null as File | null,
  })

  const selectedCourse = useMemo(
    () => courses.find((c) => c.id === selectedCourseId),
    [courses, selectedCourseId]
  )

  useEffect(() => {
    fetchCourses()
    fetchLecturers()
  }, [])

  useEffect(() => {
    if (selectedCourseId) {
      fetchLectures(selectedCourseId)
      fetchDocumentsByCourse(selectedCourseId)
    } else {
      setLectures([])
      setDocuments([])
    }
  }, [selectedCourseId])

  useEffect(() => {
    if (selectedLectureId) {
      fetchDocumentsByLecture(selectedLectureId)
    } else if (selectedCourseId) {
      fetchDocumentsByCourse(selectedCourseId)
    }
  }, [selectedLectureId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function fetchCourses() {
    try {
      setLoadingCourses(true)
      setError("")
      const res = await fetch(`${API_BASE}/courses/`)
      if (!res.ok) throw new Error("שגיאה בטעינת הקורסים")
      const data = await res.json()
      setCourses(data)
      if (!selectedCourseId && data.length > 0) {
        setSelectedCourseId(data[0].id)
      }
    } catch (err: any) {
      setError(err.message || "שגיאה בטעינת הקורסים")
    } finally {
      setLoadingCourses(false)
    }
  }

  async function fetchLecturers() {
    try {
      setLoadingLecturers(true)
      const res = await fetch(`${API_BASE}/lecturers/`)
      if (!res.ok) throw new Error("שגיאה בטעינת המרצים")
      const data = await res.json()
      setLecturers(data)
    } catch (err: any) {
      setError(err.message || "שגיאה בטעינת המרצים")
    } finally {
      setLoadingLecturers(false)
    }
  }

  async function fetchLectures(courseId: string) {
    try {
      setLoadingLectures(true)
      const res = await fetch(`${API_BASE}/lectures/course/${courseId}`)
      if (!res.ok) throw new Error("שגיאה בטעינת ההרצאות")
      const data = await res.json()
      setLectures(data)
    } catch (err: any) {
      setError(err.message || "שגיאה בטעינת ההרצאות")
    } finally {
      setLoadingLectures(false)
    }
  }

  async function fetchDocumentsByCourse(courseId: string) {
    try {
      setLoadingDocs(true)
      const res = await fetch(`${API_BASE}/documents/course/${courseId}`)
      if (!res.ok) throw new Error("שגיאה בטעינת המסמכים")
      const data = await res.json()
      setDocuments(data)
    } catch (err: any) {
      setError(err.message || "שגיאה בטעינת המסמכים")
    } finally {
      setLoadingDocs(false)
    }
  }

  async function fetchDocumentsByLecture(lectureId: string) {
    try {
      setLoadingDocs(true)
      const res = await fetch(`${API_BASE}/documents/lecture/${lectureId}`)
      if (!res.ok) throw new Error("שגיאה בטעינת מסמכי ההרצאה")
      const data = await res.json()
      setDocuments(data)
    } catch (err: any) {
      setError(err.message || "שגיאה בטעינת מסמכי ההרצאה")
    } finally {
      setLoadingDocs(false)
    }
  }

  async function createCourse() {
    if (!newCourse.name.trim()) return

    try {
      setCreatingCourse(true)
      setError("")
      const res = await fetch(`${API_BASE}/courses/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newCourse),
      })
      if (!res.ok) throw new Error("שגיאה ביצירת קורס")
      const created = await res.json()
      setCourses((prev) => [created, ...prev])
      setSelectedCourseId(created.id)
      setNewCourse({
        name: "",
        institution: "",
        default_language: "en",
        semester: "",
        lecturer_name: "",
      })
    } catch (err: any) {
      setError(err.message || "שגיאה ביצירת קורס")
    } finally {
      setCreatingCourse(false)
    }
  }

  async function createLecturer() {
    if (!newLecturer.full_name.trim()) return

    try {
      setCreatingLecturer(true)
      setError("")
      const res = await fetch(`${API_BASE}/lecturers/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newLecturer),
      })
      if (!res.ok) throw new Error("שגיאה ביצירת מרצה")
      const created = await res.json()
      setLecturers((prev) => [created, ...prev])
      setNewLecturer({ full_name: "", bio: "" })
    } catch (err: any) {
      setError(err.message || "שגיאה ביצירת מרצה")
    } finally {
      setCreatingLecturer(false)
    }
  }

  async function createLecture() {
    if (!selectedCourseId) {
      setError("יש לבחור קורס קודם")
      return
    }

    if (!newLecture.title.trim() || !newLecture.lecturer_id) {
      setError("יש למלא כותרת הרצאה ומרצה")
      return
    }

    try {
      setCreatingLecture(true)
      setError("")
      const res = await fetch(`${API_BASE}/lectures/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          course_id: selectedCourseId,
          lecturer_id: newLecture.lecturer_id,
          title: newLecture.title,
          lecture_date: newLecture.lecture_date,
          notes: newLecture.notes,
        }),
      })
      if (!res.ok) throw new Error("שגיאה ביצירת הרצאה")
      const created = await res.json()
      await fetchLectures(selectedCourseId)
      setSelectedLectureId(created.id)
      setNewLecture({
        title: "",
        lecturer_id: "",
        lecture_date: "",
        notes: "",
      })
    } catch (err: any) {
      setError(err.message || "שגיאה ביצירת הרצאה")
    } finally {
      setCreatingLecture(false)
    }
  }

  async function uploadFile() {
    if (!selectedCourseId) {
      setError("יש לבחור קורס")
      return
    }
    if (!selectedLectureId) {
      setError("יש לבחור הרצאה")
      return
    }
    if (!uploadForm.file) {
      setError("יש לבחור קובץ")
      return
    }

    try {
      setUploading(true)
      setError("")
      const formData = new FormData()
      formData.append("course_id", selectedCourseId)
      formData.append("lecture_id", selectedLectureId)
      formData.append("topic", uploadForm.topic)
      formData.append("source_type", uploadForm.source_type)
      formData.append("file", uploadForm.file)

      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      })
      if (!res.ok) throw new Error("שגיאה בהעלאת קובץ")

      await fetchDocumentsByLecture(selectedLectureId)

      setUploadForm({
        topic: "",
        source_type: "slides",
        file: null,
      })
    } catch (err: any) {
      setError(err.message || "שגיאה בהעלאת קובץ")
    } finally {
      setUploading(false)
    }
  }

  async function sendMessage() {
    if (!input.trim() || !selectedCourseId || sending) return

    const userText = input
    const userMessage: Message = { role: "user", content: userText }

    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setSending(true)
    setError("")

    const assistantIndex = messages.length + 1

    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: "",
        intent: "",
        sources: [],
      },
    ])

    try {
      const res = await fetch(`${API_BASE}/copilot/ask-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          course_id: selectedCourseId,
          question: userText,
        }),
      })

      if (!res.ok || !res.body) {
        throw new Error("שגיאה בקבלת תשובת הסוכן")
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""

        for (const line of lines) {
          if (!line.trim()) continue
          const event = JSON.parse(line)

          if (event.type === "meta") {
            setMessages((prev) => {
              const updated = [...prev]
              updated[assistantIndex] = {
                ...updated[assistantIndex],
                intent: event.intent,
                sources: event.sources || [],
              }
              return updated
            })
          }

          if (event.type === "chunk") {
            setMessages((prev) => {
              const updated = [...prev]
              updated[assistantIndex] = {
                ...updated[assistantIndex],
                content: (updated[assistantIndex]?.content || "") + event.content,
              }
              return updated
            })
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "שגיאה בקבלת תשובת הסוכן")
    } finally {
      setSending(false)
    }
  }

  return (
    <div dir="rtl" className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto max-w-7xl p-6">
        <h1 className="text-4xl font-bold mb-6">קופיילוט למידה מבוסס AI</h1>

        {error && (
          <div className="mb-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 lg:col-span-3 space-y-6">
            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">קורסים</h2>

              {loadingCourses ? (
                <p className="text-sm text-slate-500">טוען קורסים...</p>
              ) : courses.length === 0 ? (
                <p className="text-sm text-slate-500">עדיין אין קורסים.</p>
              ) : (
                <div className="space-y-2">
                  {courses.map((course) => (
                    <button
                      key={course.id}
                      onClick={() => {
                        setSelectedCourseId(course.id)
                        setSelectedLectureId("")
                      }}
                      className={`w-full rounded-xl border px-3 py-3 text-right transition ${
                        selectedCourseId === course.id
                          ? "border-blue-500 bg-blue-50"
                          : "border-slate-200 bg-white hover:bg-slate-50"
                      }`}
                    >
                      <div className="font-medium">{course.name}</div>
                      <div className="text-xs text-slate-500">
                        {course.institution || "ללא מוסד"}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">יצירת קורס</h2>

              <div className="space-y-3">
                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="שם קורס"
                  value={newCourse.name}
                  onChange={(e) =>
                    setNewCourse((prev) => ({ ...prev, name: e.target.value }))
                  }
                />

                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="מוסד"
                  value={newCourse.institution}
                  onChange={(e) =>
                    setNewCourse((prev) => ({ ...prev, institution: e.target.value }))
                  }
                />

                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="סמסטר"
                  value={newCourse.semester}
                  onChange={(e) =>
                    setNewCourse((prev) => ({ ...prev, semester: e.target.value }))
                  }
                />

                <button
                  onClick={createCourse}
                  disabled={creatingCourse}
                  className="w-full rounded-lg bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-50"
                >
                  {creatingCourse ? "יוצר..." : "צור קורס"}
                </button>
              </div>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">יצירת מרצה</h2>

              <div className="space-y-3">
                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="שם המרצה"
                  value={newLecturer.full_name}
                  onChange={(e) =>
                    setNewLecturer((prev) => ({ ...prev, full_name: e.target.value }))
                  }
                />

                <textarea
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="ביוגרפיה / הערות"
                  value={newLecturer.bio}
                  onChange={(e) =>
                    setNewLecturer((prev) => ({ ...prev, bio: e.target.value }))
                  }
                />

                <button
                  onClick={createLecturer}
                  disabled={creatingLecturer}
                  className="w-full rounded-lg bg-slate-800 px-4 py-2 font-medium text-white disabled:opacity-50"
                >
                  {creatingLecturer ? "יוצר..." : "צור מרצה"}
                </button>
              </div>
            </section>
          </aside>

          <main className="col-span-12 lg:col-span-9 space-y-6">
            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-2xl font-semibold">
                {selectedCourse?.name || "בחר קורס"}
              </h2>
              <p className="text-sm text-slate-500 mt-1">
                {selectedCourse?.institution || "ללא מוסד"} •{" "}
                {selectedCourse?.semester || "ללא סמסטר"}
              </p>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">הרצאות בקורס</h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <input
                  className="rounded-lg border px-3 py-2"
                  placeholder="כותרת הרצאה"
                  value={newLecture.title}
                  onChange={(e) =>
                    setNewLecture((prev) => ({ ...prev, title: e.target.value }))
                  }
                />

                <select
                  className="rounded-lg border px-3 py-2"
                  value={newLecture.lecturer_id}
                  onChange={(e) =>
                    setNewLecture((prev) => ({
                      ...prev,
                      lecturer_id: e.target.value,
                    }))
                  }
                >
                  <option value="">בחר מרצה</option>
                  {lecturers.map((lecturer) => (
                    <option key={lecturer.id} value={lecturer.id}>
                      {lecturer.full_name}
                    </option>
                  ))}
                </select>

                <input
                  className="rounded-lg border px-3 py-2"
                  placeholder="תאריך הרצאה"
                  value={newLecture.lecture_date}
                  onChange={(e) =>
                    setNewLecture((prev) => ({
                      ...prev,
                      lecture_date: e.target.value,
                    }))
                  }
                />

                <input
                  className="rounded-lg border px-3 py-2"
                  placeholder="הערות"
                  value={newLecture.notes}
                  onChange={(e) =>
                    setNewLecture((prev) => ({ ...prev, notes: e.target.value }))
                  }
                />
              </div>

              <button
                onClick={createLecture}
                disabled={creatingLecture || !selectedCourseId}
                className="mt-4 rounded-lg bg-purple-600 px-4 py-2 font-medium text-white disabled:opacity-50"
              >
                {creatingLecture ? "יוצר..." : "צור הרצאה"}
              </button>

              <div className="mt-4 space-y-2">
                {loadingLectures ? (
                  <p className="text-sm text-slate-500">טוען הרצאות...</p>
                ) : lectures.length === 0 ? (
                  <p className="text-sm text-slate-500">עדיין אין הרצאות.</p>
                ) : (
                  lectures.map((lecture) => (
                    <button
                      key={lecture.id}
                      onClick={() => setSelectedLectureId(lecture.id)}
                      className={`w-full rounded-xl border px-3 py-3 text-right ${
                        selectedLectureId === lecture.id
                          ? "border-purple-500 bg-purple-50"
                          : "border-slate-200 bg-white"
                      }`}
                    >
                      <div className="font-medium">{lecture.title}</div>
                      <div className="text-xs text-slate-500">
                        {lecture.lecturer_name || "ללא מרצה"} •{" "}
                        {lecture.lecture_date || "ללא תאריך"}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">העלאת חומר להרצאה</h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  className="rounded-lg border px-3 py-2"
                  placeholder="נושא"
                  value={uploadForm.topic}
                  onChange={(e) =>
                    setUploadForm((prev) => ({ ...prev, topic: e.target.value }))
                  }
                />

                <select
                  className="rounded-lg border px-3 py-2"
                  value={uploadForm.source_type}
                  onChange={(e) =>
                    setUploadForm((prev) => ({
                      ...prev,
                      source_type: e.target.value,
                    }))
                  }
                >
                  <option value="slides">מצגת</option>
                  <option value="summary">סיכום</option>
                  <option value="notes">הערות</option>
                  <option value="article">מאמר</option>
                </select>

                <input
                  className="rounded-lg border px-3 py-2"
                  type="file"
                  onChange={(e) =>
                    setUploadForm((prev) => ({
                      ...prev,
                      file: e.target.files?.[0] || null,
                    }))
                  }
                />
              </div>

              <button
                onClick={uploadFile}
                disabled={uploading || !selectedCourseId || !selectedLectureId}
                className="mt-4 rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-50"
              >
                {uploading ? "מעלה..." : "העלה חומר להרצאה"}
              </button>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">מסמכים</h2>

              {loadingDocs ? (
                <p className="text-sm text-slate-500">טוען מסמכים...</p>
              ) : documents.length === 0 ? (
                <p className="text-sm text-slate-500">אין מסמכים להצגה.</p>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="rounded-xl border border-slate-200 px-3 py-3"
                    >
                      <div className="font-medium">{doc.file_name}</div>
                      <div className="text-xs text-slate-500">
                        {doc.lecture_title ? `${doc.lecture_title} • ` : ""}
                        {doc.file_type || "unknown"} • {doc.language || "unknown"} •{" "}
                        {doc.topic || "ללא נושא"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">צ׳אט עם הסוכן</h2>

              <div className="h-[520px] overflow-y-auto rounded-xl border p-4 bg-slate-50">
                {messages.length === 0 ? (
                  <p className="text-sm text-slate-500">
                    אפשר לשאול בעברית או באנגלית.
                    <br />
                    התשובה תחזור באותה שפה.
                    <br />
                    לדוגמה:
                    <br />
                    • מהם הנושאים המרכזיים בקורס?
                    <br />
                    • Generate exam questions
                    <br />
                    • סכם את הקורס
                  </p>
                ) : (
                  <div className="space-y-4">
                    {messages.map((m, i) => (
                      <div
                        key={i}
                        className={`max-w-[88%] rounded-2xl px-4 py-3 shadow-sm ${
                          m.role === "user"
                            ? "mr-auto bg-blue-600 text-white"
                            : "ml-auto bg-white border border-slate-200 text-slate-900"
                        }`}
                      >
                        <div className="mb-2 text-xs font-semibold uppercase tracking-wide opacity-70">
                          {m.role === "user" ? "אתה" : "הסוכן"}
                          {m.intent ? ` • ${m.intent}` : ""}
                        </div>

                        <div className={`prose prose-sm max-w-none ${m.role === "user" ? "prose-invert" : ""}`}>
                          <ReactMarkdown>{m.content}</ReactMarkdown>
                        </div>

                        {m.sources && m.sources.length > 0 && (
                          <div className="mt-3 border-t pt-3">
                            <div className="text-xs font-semibold mb-2 opacity-70">
                              מקורות
                            </div>
                            <div className="space-y-1">
                              {m.sources.map((s, idx) => (
                                <div key={idx} className="text-xs opacity-80">
                                  מסמך: {s.document_id || "n/a"} • chunk:{" "}
                                  {typeof s.chunk_index === "number" ? s.chunk_index : "n/a"}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <input
                  className="flex-1 rounded-xl border px-4 py-3"
                  placeholder="שאל שאלה על הקורס..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") sendMessage()
                  }}
                />

                <button
                  onClick={sendMessage}
                  disabled={sending || !selectedCourseId}
                  className="rounded-xl bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50"
                >
                  {sending ? "חושב..." : "שלח"}
                </button>
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  )
}
EOF

echo "Hebrew domain UI upgraded successfully."
