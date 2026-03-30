#!/bin/bash

set -e

echo "Installing UI packages..."
npm install react-markdown

echo "Writing .env.local..."
cat > .env.local <<'EOF'
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
EOF

echo "Writing app/page.tsx..."
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
  default_language?: string
  semester?: string
  lecturer_name?: string
  created_at?: string
}

type CourseDocument = {
  id: string
  course_id: string
  file_name: string
  file_type?: string
  language?: string
  session_number?: string
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
  const [selectedCourseId, setSelectedCourseId] = useState<string>("")
  const [documents, setDocuments] = useState<CourseDocument[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [loadingCourses, setLoadingCourses] = useState(false)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [sending, setSending] = useState(false)
  const [creatingCourse, setCreatingCourse] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  const [newCourse, setNewCourse] = useState({
    name: "",
    institution: "",
    default_language: "en",
    semester: "",
    lecturer_name: "",
  })

  const [uploadForm, setUploadForm] = useState({
    session_number: "",
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
  }, [])

  useEffect(() => {
    if (selectedCourseId) {
      fetchDocuments(selectedCourseId)
    } else {
      setDocuments([])
    }
  }, [selectedCourseId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function fetchCourses() {
    try {
      setLoadingCourses(true)
      setError("")
      const res = await fetch(`${API_BASE}/courses/`)
      if (!res.ok) throw new Error("Failed to load courses")
      const data = await res.json()
      setCourses(data)

      if (!selectedCourseId && data.length > 0) {
        setSelectedCourseId(data[0].id)
      }
    } catch (err: any) {
      setError(err.message || "Failed to load courses")
    } finally {
      setLoadingCourses(false)
    }
  }

  async function fetchDocuments(courseId: string) {
    try {
      setLoadingDocs(true)
      setError("")
      const res = await fetch(`${API_BASE}/documents/course/${courseId}`)
      if (!res.ok) throw new Error("Failed to load documents")
      const data = await res.json()
      setDocuments(data)
    } catch (err: any) {
      setError(err.message || "Failed to load documents")
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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newCourse),
      })

      if (!res.ok) throw new Error("Failed to create course")

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
      setError(err.message || "Failed to create course")
    } finally {
      setCreatingCourse(false)
    }
  }

  async function uploadFile() {
    if (!selectedCourseId) {
      setError("Please select a course first")
      return
    }

    if (!uploadForm.file) {
      setError("Please choose a file to upload")
      return
    }

    try {
      setUploading(true)
      setError("")

      const formData = new FormData()
      formData.append("course_id", selectedCourseId)
      formData.append("session_number", uploadForm.session_number)
      formData.append("topic", uploadForm.topic)
      formData.append("source_type", uploadForm.source_type)
      formData.append("file", uploadForm.file)

      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      })

      if (!res.ok) throw new Error("Failed to upload file")

      await fetchDocuments(selectedCourseId)

      setUploadForm({
        session_number: "",
        topic: "",
        source_type: "slides",
        file: null,
      })
    } catch (err: any) {
      setError(err.message || "Failed to upload file")
    } finally {
      setUploading(false)
    }
  }

  async function sendMessage() {
    if (!input.trim() || !selectedCourseId || sending) return

    const userText = input
    const userMessage: Message = {
      role: "user",
      content: userText,
    }

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
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          course_id: selectedCourseId,
          question: userText,
          language: selectedCourse?.default_language || "en",
        }),
      })

      if (!res.ok || !res.body) {
        throw new Error("Failed to stream copilot response")
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
      setError(err.message || "Failed to get copilot response")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto max-w-7xl p-6">
        <h1 className="text-4xl font-bold mb-6">AI Learning Copilot</h1>

        {error && (
          <div className="mb-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 lg:col-span-3 space-y-6">
            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">Courses</h2>

              {loadingCourses ? (
                <p className="text-sm text-slate-500">Loading courses...</p>
              ) : courses.length === 0 ? (
                <p className="text-sm text-slate-500">No courses yet.</p>
              ) : (
                <div className="space-y-2">
                  {courses.map((course) => (
                    <button
                      key={course.id}
                      onClick={() => setSelectedCourseId(course.id)}
                      className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                        selectedCourseId === course.id
                          ? "border-blue-500 bg-blue-50"
                          : "border-slate-200 bg-white hover:bg-slate-50"
                      }`}
                    >
                      <div className="font-medium">{course.name}</div>
                      <div className="text-xs text-slate-500">
                        {course.institution || "No institution"}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">Create Course</h2>

              <div className="space-y-3">
                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="Course name"
                  value={newCourse.name}
                  onChange={(e) =>
                    setNewCourse((prev) => ({ ...prev, name: e.target.value }))
                  }
                />

                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="Institution"
                  value={newCourse.institution}
                  onChange={(e) =>
                    setNewCourse((prev) => ({
                      ...prev,
                      institution: e.target.value,
                    }))
                  }
                />

                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="Semester"
                  value={newCourse.semester}
                  onChange={(e) =>
                    setNewCourse((prev) => ({
                      ...prev,
                      semester: e.target.value,
                    }))
                  }
                />

                <input
                  className="w-full rounded-lg border px-3 py-2"
                  placeholder="Lecturer name"
                  value={newCourse.lecturer_name}
                  onChange={(e) =>
                    setNewCourse((prev) => ({
                      ...prev,
                      lecturer_name: e.target.value,
                    }))
                  }
                />

                <select
                  className="w-full rounded-lg border px-3 py-2"
                  value={newCourse.default_language}
                  onChange={(e) =>
                    setNewCourse((prev) => ({
                      ...prev,
                      default_language: e.target.value,
                    }))
                  }
                >
                  <option value="en">English</option>
                  <option value="he">Hebrew</option>
                </select>

                <button
                  onClick={createCourse}
                  disabled={creatingCourse}
                  className="w-full rounded-lg bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-50"
                >
                  {creatingCourse ? "Creating..." : "Create Course"}
                </button>
              </div>
            </section>
          </aside>

          <main className="col-span-12 lg:col-span-9 space-y-6">
            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-semibold">
                    {selectedCourse?.name || "Select a course"}
                  </h2>
                  <p className="text-sm text-slate-500">
                    {selectedCourse?.institution || "No institution"} •{" "}
                    {selectedCourse?.default_language || "en"} •{" "}
                    {selectedCourse?.semester || "No semester"}
                  </p>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">Upload Material</h2>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <input
                  className="rounded-lg border px-3 py-2"
                  placeholder="Session number"
                  value={uploadForm.session_number}
                  onChange={(e) =>
                    setUploadForm((prev) => ({
                      ...prev,
                      session_number: e.target.value,
                    }))
                  }
                />

                <input
                  className="rounded-lg border px-3 py-2"
                  placeholder="Topic"
                  value={uploadForm.topic}
                  onChange={(e) =>
                    setUploadForm((prev) => ({
                      ...prev,
                      topic: e.target.value,
                    }))
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
                  <option value="slides">slides</option>
                  <option value="summary">summary</option>
                  <option value="notes">notes</option>
                  <option value="article">article</option>
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
                disabled={uploading || !selectedCourseId}
                className="mt-4 rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-50"
              >
                {uploading ? "Uploading..." : "Upload to Course"}
              </button>
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">Course Documents</h2>

              {loadingDocs ? (
                <p className="text-sm text-slate-500">Loading documents...</p>
              ) : documents.length === 0 ? (
                <p className="text-sm text-slate-500">No documents uploaded yet.</p>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="rounded-xl border border-slate-200 px-3 py-3"
                    >
                      <div className="font-medium">{doc.file_name}</div>
                      <div className="text-xs text-slate-500">
                        {doc.file_type || "unknown"} • {doc.language || "unknown"} • session{" "}
                        {doc.session_number || "-"} • {doc.topic || "No topic"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-2xl border bg-white p-4 shadow-sm">
              <h2 className="text-xl font-semibold mb-4">Copilot Chat</h2>

              <div className="h-[520px] overflow-y-auto rounded-xl border p-4 bg-slate-50">
                {messages.length === 0 ? (
                  <p className="text-sm text-slate-500">
                    Ask about the selected course. Try:
                    <br />
                    • What are the main topics in this course?
                    <br />
                    • Generate exam questions
                    <br />
                    • Summarize the whole course
                  </p>
                ) : (
                  <div className="space-y-4">
                    {messages.map((m, i) => (
                      <div
                        key={i}
                        className={`max-w-[88%] rounded-2xl px-4 py-3 shadow-sm ${
                          m.role === "user"
                            ? "ml-auto bg-blue-600 text-white"
                            : "mr-auto bg-white border border-slate-200 text-slate-900"
                        }`}
                      >
                        <div className="mb-2 text-xs font-semibold uppercase tracking-wide opacity-70">
                          {m.role === "user" ? "You" : "Copilot"}
                          {m.intent ? ` • ${m.intent}` : ""}
                        </div>

                        <div className={`prose prose-sm max-w-none ${m.role === "user" ? "prose-invert" : ""}`}>
                          <ReactMarkdown>{m.content}</ReactMarkdown>
                        </div>

                        {m.sources && m.sources.length > 0 && (
                          <div className="mt-3 border-t pt-3">
                            <div className="text-xs font-semibold mb-2 opacity-70">
                              Sources
                            </div>
                            <div className="space-y-1">
                              {m.sources.map((s, idx) => (
                                <div
                                  key={idx}
                                  className="text-xs opacity-80"
                                >
                                  document: {s.document_id || "n/a"} • chunk:{" "}
                                  {typeof s.chunk_index === "number"
                                    ? s.chunk_index
                                    : "n/a"}
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
                  placeholder="Ask about the selected course..."
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
                  {sending ? "Thinking..." : "Send"}
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

echo "Streaming ChatGPT-style UI upgraded successfully."
