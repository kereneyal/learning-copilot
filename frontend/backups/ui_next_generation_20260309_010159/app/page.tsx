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
  course_id?: string
  course_name?: string
  lecture_id?: string
  lecture_title?: string
  document_id?: string
  document_name?: string
  snippet?: string
  chunk_index?: number
}

type Message = {
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  mode?: string
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
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")
  const [chatMode, setChatMode] = useState<"auto" | "global" | "course" | "lecture">("auto")
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
    }
  }, [selectedLectureId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function fetchCourses() {
    const res = await fetch(`${API_BASE}/courses/`)
    const data = await res.json()
    setCourses(data)
    if (data.length > 0 && !selectedCourseId) {
      setSelectedCourseId(data[0].id)
    }
  }

  async function fetchLecturers() {
    const res = await fetch(`${API_BASE}/lecturers/`)
    const data = await res.json()
    setLecturers(data)
  }

  async function fetchLectures(courseId: string) {
    const res = await fetch(`${API_BASE}/lectures/course/${courseId}`)
    const data = await res.json()
    setLectures(data)
  }

  async function fetchDocumentsByCourse(courseId: string) {
    const res = await fetch(`${API_BASE}/documents/course/${courseId}`)
    const data = await res.json()
    setDocuments(data)
  }

  async function fetchDocumentsByLecture(lectureId: string) {
    const res = await fetch(`${API_BASE}/documents/lecture/${lectureId}`)
    const data = await res.json()
    setDocuments(data)
  }

  async function createCourse() {
    if (!newCourse.name.trim()) return

    const res = await fetch(`${API_BASE}/courses/`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(newCourse),
    })

    if (!res.ok) {
      setError("שגיאה ביצירת קורס")
      return
    }

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
  }

  async function createLecturer() {
    if (!newLecturer.full_name.trim()) return

    const res = await fetch(`${API_BASE}/lecturers/`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(newLecturer),
    })

    if (!res.ok) {
      setError("שגיאה ביצירת מרצה")
      return
    }

    const created = await res.json()
    setLecturers((prev) => [created, ...prev])
    setNewLecturer({ full_name: "", bio: "" })
  }

  async function createLecture() {
    if (!selectedCourseId || !newLecture.title.trim() || !newLecture.lecturer_id) {
      setError("יש לבחור קורס ולמלא כותרת ומרצה")
      return
    }

    const res = await fetch(`${API_BASE}/lectures/`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        course_id: selectedCourseId,
        lecturer_id: newLecture.lecturer_id,
        title: newLecture.title,
        lecture_date: newLecture.lecture_date,
        notes: newLecture.notes,
      }),
    })

    if (!res.ok) {
      setError("שגיאה ביצירת הרצאה")
      return
    }

    const created = await res.json()
    await fetchLectures(selectedCourseId)
    setSelectedLectureId(created.id)
    setNewLecture({
      title: "",
      lecturer_id: "",
      lecture_date: "",
      notes: "",
    })
  }

  async function uploadFile() {
    if (!selectedCourseId || !selectedLectureId || !uploadForm.file) {
      setError("יש לבחור קורס, הרצאה וקובץ")
      return
    }

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

    if (!res.ok) {
      setError("שגיאה בהעלאת קובץ")
      return
    }

    await fetchDocumentsByLecture(selectedLectureId)
    setUploadForm({
      topic: "",
      source_type: "slides",
      file: null,
    })
  }

  async function sendMessage() {
    if (!input.trim() || sending) return

    const userText = input
    setMessages((prev) => [...prev, { role: "user", content: userText }])
    setInput("")
    setSending(true)
    setError("")

    try {
      const body: any = {
        question: userText,
        mode: chatMode,
      }

      if (chatMode === "course" || chatMode === "lecture") {
        body.course_id = selectedCourseId
      }

      if (chatMode === "lecture") {
        body.lecture_id = selectedLectureId
      }

      const res = await fetch(`${API_BASE}/copilot/ask`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        setError("שגיאה בקבלת תשובת הסוכן")
        setSending(false)
        return
      }

      const data = await res.json()

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources || [],
          mode: data.mode,
        },
      ])
    } catch (e) {
      setError("שגיאה בקבלת תשובת הסוכן")
    } finally {
      setSending(false)
    }
  }

  return (
    <div dir="rtl" className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto max-w-7xl p-6">
        <h1 className="mb-6 text-4xl font-bold">קופיילוט למידה מבוסס AI</h1>

        {error && (
          <div className="mb-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 lg:col-span-3 space-y-6">
            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold">קורסים</h2>
              <div className="space-y-2">
                {courses.map((course) => (
                  <button
                    key={course.id}
                    onClick={() => {
                      setSelectedCourseId(course.id)
                      setSelectedLectureId("")
                    }}
                    className={`w-full rounded-xl border px-3 py-3 text-right ${
                      selectedCourseId === course.id
                        ? "border-blue-500 bg-blue-50"
                        : "border-slate-200 bg-white"
                    }`}
                  >
                    <div className="font-medium">{course.name}</div>
                    <div className="text-xs text-slate-500">
                      {course.institution || "ללא מוסד"}
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold">יצירת קורס</h2>
              <div className="space-y-3">
                <input className="w-full rounded-lg border px-3 py-2" placeholder="שם קורס" value={newCourse.name} onChange={(e) => setNewCourse((p) => ({ ...p, name: e.target.value }))} />
                <input className="w-full rounded-lg border px-3 py-2" placeholder="מוסד" value={newCourse.institution} onChange={(e) => setNewCourse((p) => ({ ...p, institution: e.target.value }))} />
                <input className="w-full rounded-lg border px-3 py-2" placeholder="סמסטר" value={newCourse.semester} onChange={(e) => setNewCourse((p) => ({ ...p, semester: e.target.value }))} />
                <button onClick={createCourse} className="w-full rounded-lg bg-blue-600 px-4 py-2 font-medium text-white">צור קורס</button>
              </div>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold">יצירת מרצה</h2>
              <div className="space-y-3">
                <input className="w-full rounded-lg border px-3 py-2" placeholder="שם המרצה" value={newLecturer.full_name} onChange={(e) => setNewLecturer((p) => ({ ...p, full_name: e.target.value }))} />
                <textarea className="w-full rounded-lg border px-3 py-2" placeholder="ביוגרפיה / הערות" value={newLecturer.bio} onChange={(e) => setNewLecturer((p) => ({ ...p, bio: e.target.value }))} />
                <button onClick={createLecturer} className="w-full rounded-lg bg-slate-800 px-4 py-2 font-medium text-white">צור מרצה</button>
              </div>
            </section>
          </aside>

          <main className="col-span-12 lg:col-span-9 space-y-6">
            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-2xl font-semibold">{selectedCourse?.name || "בחר קורס"}</h2>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold">הרצאות בקורס</h2>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                <input className="rounded-lg border px-3 py-2" placeholder="כותרת הרצאה" value={newLecture.title} onChange={(e) => setNewLecture((p) => ({ ...p, title: e.target.value }))} />
                <select className="rounded-lg border px-3 py-2" value={newLecture.lecturer_id} onChange={(e) => setNewLecture((p) => ({ ...p, lecturer_id: e.target.value }))}>
                  <option value="">בחר מרצה</option>
                  {lecturers.map((lecturer) => (
                    <option key={lecturer.id} value={lecturer.id}>{lecturer.full_name}</option>
                  ))}
                </select>
                <input className="rounded-lg border px-3 py-2" placeholder="תאריך הרצאה" value={newLecture.lecture_date} onChange={(e) => setNewLecture((p) => ({ ...p, lecture_date: e.target.value }))} />
                <input className="rounded-lg border px-3 py-2" placeholder="הערות" value={newLecture.notes} onChange={(e) => setNewLecture((p) => ({ ...p, notes: e.target.value }))} />
              </div>

              <button onClick={createLecture} className="mt-4 rounded-lg bg-purple-600 px-4 py-2 font-medium text-white">צור הרצאה</button>

              <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2">
                {lectures.map((lecture) => (
                  <button
                    key={lecture.id}
                    onClick={() => setSelectedLectureId(lecture.id)}
                    className={`rounded-xl border px-3 py-3 text-right ${
                      selectedLectureId === lecture.id
                        ? "border-purple-500 bg-purple-50"
                        : "border-slate-200 bg-white"
                    }`}
                  >
                    <div className="font-medium">{lecture.title}</div>
                    <div className="text-xs text-slate-500">
                      {lecture.lecturer_name || "ללא מרצה"} • {lecture.lecture_date || "ללא תאריך"}
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <div className="rounded-2xl border bg-white p-4 shadow-sm">
                <h2 className="mb-4 text-xl font-semibold">העלאת חומר להרצאה</h2>
                <div className="space-y-3">
                  <input className="w-full rounded-lg border px-3 py-2" placeholder="נושא" value={uploadForm.topic} onChange={(e) => setUploadForm((p) => ({ ...p, topic: e.target.value }))} />
                  <select className="w-full rounded-lg border px-3 py-2" value={uploadForm.source_type} onChange={(e) => setUploadForm((p) => ({ ...p, source_type: e.target.value }))}>
                    <option value="slides">מצגת</option>
                    <option value="summary">סיכום</option>
                    <option value="notes">הערות</option>
                    <option value="article">מאמר</option>
                  </select>
                  <input className="w-full rounded-lg border px-3 py-2" type="file" onChange={(e) => setUploadForm((p) => ({ ...p, file: e.target.files?.[0] || null }))} />
                  <button onClick={uploadFile} className="w-full rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white">העלה חומר להרצאה</button>
                </div>
              </div>

              <div className="rounded-2xl border bg-white p-4 shadow-sm">
                <h2 className="mb-4 text-xl font-semibold">מסמכים</h2>
                <div className="max-h-[280px] space-y-2 overflow-y-auto">
                  {documents.map((doc) => (
                    <div key={doc.id} className="rounded-xl border border-slate-200 px-3 py-3">
                      <div className="font-medium">{doc.file_name}</div>
                      <div className="text-xs text-slate-500">
                        {doc.lecture_title ? `${doc.lecture_title} • ` : ""}
                        {doc.file_type || "unknown"} • {doc.language || "unknown"} • {doc.topic || "ללא נושא"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="mb-4 text-xl font-semibold">צ׳אט עם הסוכן</h2>

              <div className="mb-4 flex flex-wrap gap-2">
                <button onClick={() => setChatMode("auto")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "auto" ? "bg-blue-600 text-white" : "bg-slate-200"}`}>אוטומטי</button>
                <button onClick={() => setChatMode("global")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "global" ? "bg-blue-600 text-white" : "bg-slate-200"}`}>כל הקורסים</button>
                <button onClick={() => setChatMode("course")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "course" ? "bg-blue-600 text-white" : "bg-slate-200"}`}>הקורס הנוכחי</button>
                <button onClick={() => setChatMode("lecture")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "lecture" ? "bg-blue-600 text-white" : "bg-slate-200"}`}>ההרצאה הנוכחית</button>
              </div>

              <div className="h-[520px] overflow-y-auto rounded-2xl border bg-slate-50 p-4">
                {messages.length === 0 ? (
                  <p className="text-sm text-slate-500">
                    אפשר לשאול בעברית או באנגלית.
                    <br />
                    המקורות יוצגו עם שם קורס, הרצאה ומסמך.
                  </p>
                ) : (
                  <div className="space-y-4">
                    {messages.map((m, i) => (
                      <div key={i} className={`flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${m.role === "user" ? "bg-blue-600 text-white" : "border border-slate-200 bg-white text-slate-900"}`}>
                          <div className="mb-2 text-xs font-semibold opacity-70">
                            {m.role === "user" ? "אתה" : `הסוכן${m.mode ? ` • ${m.mode}` : ""}`}
                          </div>

                          <div className={`prose prose-sm max-w-none ${m.role === "user" ? "prose-invert" : ""}`}>
                            <ReactMarkdown>{m.content}</ReactMarkdown>
                          </div>

                          {m.sources && m.sources.length > 0 && (
                            <div className="mt-3 border-t pt-3">
                              <div className="mb-2 text-xs font-semibold opacity-70">מקורות</div>
                              <div className="space-y-3">
                                {m.sources.map((s, idx) => (
                                  <div key={idx} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
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
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <input
                  className="flex-1 rounded-xl border px-4 py-3"
                  placeholder="שאל שאלה על הידע שבמערכת..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") sendMessage()
                  }}
                />
                <button onClick={sendMessage} disabled={sending} className="rounded-xl bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50">
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
