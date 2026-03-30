"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import CourseContextBar from "./CourseContextBar"
import SourcePanel from "./SourcePanel"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"

type Course = {
  id: string
  name: string
  institution?: string
  semester?: string
}

type Lecture = {
  id: string
  course_id: string
  lecturer_id: string
  lecturer_name?: string
  title: string
  lecture_date?: string
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

export default function ChatWorkspace() {
  const [courses, setCourses] = useState<Course[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")
  const [chatMode, setChatMode] = useState<"auto" | "global" | "course" | "lecture">("auto")
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const selectedCourse = useMemo(
    () => courses.find((c) => c.id === selectedCourseId),
    [courses, selectedCourseId]
  )

  const selectedLecture = useMemo(
    () => lectures.find((l) => l.id === selectedLectureId),
    [lectures, selectedLectureId]
  )

  const latestAssistantSources = useMemo(() => {
    const reversed = [...messages].reverse()
    const lastAssistant = reversed.find((m) => m.role === "assistant")
    return lastAssistant?.sources || []
  }, [messages])

  useEffect(() => {
    fetchCourses()
  }, [])

  useEffect(() => {
    if (selectedCourseId) {
      fetchLectures(selectedCourseId)
    } else {
      setLectures([])
    }
  }, [selectedCourseId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function fetchCourses() {
    const res = await fetch(`${API_BASE}/courses/`)
    const data = await res.json()
    setCourses(data)
    if (data.length > 0 && !selectedCourseId) {
      setSelectedCourseId(data[0].id)
    }
  }

  async function fetchLectures(courseId: string) {
    const res = await fetch(`${API_BASE}/lectures/course/${courseId}`)
    const data = await res.json()
    setLectures(data)
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
        headers: { "Content-Type": "application/json" },
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
    } catch {
      setError("שגיאה בקבלת תשובת הסוכן")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="space-y-6">
      <CourseContextBar
        selectedCourse={selectedCourse}
        selectedLecture={selectedLecture}
        chatMode={chatMode}
        setChatMode={setChatMode}
      />

      {error && (
        <div className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        <section className="col-span-12 xl:col-span-8 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">שיחה</h3>
            <div className="text-sm text-slate-500">
              {selectedCourse ? `קורס: ${selectedCourse.name}` : "ללא קורס"}
            </div>
          </div>

          <div className="h-[560px] overflow-y-auto rounded-2xl border bg-slate-50 p-4">
            {messages.length === 0 ? (
              <div className="space-y-3 text-sm text-slate-500">
                <p>אפשר לשאול בעברית או באנגלית.</p>
                <p>דוגמאות:</p>
                <ul className="list-disc pr-5">
                  <li>סכם לי את ההרצאה האחרונה</li>
                  <li>What is fiduciary duty?</li>
                  <li>באיזה קורס דיברו על governance?</li>
                </ul>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((m, i) => (
                  <div key={i} className={`flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${
                        m.role === "user"
                          ? "bg-blue-600 text-white"
                          : "border border-slate-200 bg-white text-slate-900"
                      }`}
                    >
                      <div className="mb-2 text-xs font-semibold opacity-70">
                        {m.role === "user" ? "אתה" : `הסוכן${m.mode ? ` • ${m.mode}` : ""}`}
                      </div>
                      <div className={`prose prose-sm max-w-none ${m.role === "user" ? "prose-invert" : ""}`}>
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
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
            <button
              onClick={sendMessage}
              disabled={sending}
              className="rounded-xl bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50"
            >
              {sending ? "חושב..." : "שלח"}
            </button>
          </div>
        </section>

        <div className="col-span-12 xl:col-span-4">
          <SourcePanel sources={latestAssistantSources} />
        </div>
      </div>
    </div>
  )
}
