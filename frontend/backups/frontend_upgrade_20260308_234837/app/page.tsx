"use client"

import { useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"

const API =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"

type Course = {
  id: string
  name: string
}

type Message = {
  role: "user" | "assistant"
  content: string
  intent?: string
  sources?: any[]
}

export default function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [selectedCourse, setSelectedCourse] = useState<string>("")
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchCourses()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function fetchCourses() {
    const res = await fetch(`${API}/courses/`)
    const data = await res.json()
    setCourses(data)
    if (data.length > 0) {
      setSelectedCourse(data[0].id)
    }
  }

  async function sendMessage() {
    if (!input.trim()) return

    const question = input

    setMessages((m) => [...m, { role: "user", content: question }])
    setInput("")
    setSending(true)

    const res = await fetch(`${API}/copilot/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        course_id: selectedCourse,
        question,
      }),
    })

    const data = await res.json()

    setMessages((m) => [
      ...m,
      {
        role: "assistant",
        content: data.answer,
        intent: data.intent,
        sources: data.sources,
      },
    ])

    setSending(false)
  }

  return (
    <div dir="rtl" className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-6xl mx-auto">

        <h1 className="text-4xl font-bold mb-6">
          קופיילוט למידה
        </h1>

        <div className="mb-6">
          <select
            className="border rounded-lg px-4 py-2"
            value={selectedCourse}
            onChange={(e) => setSelectedCourse(e.target.value)}
          >
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="bg-white rounded-xl p-6 h-[500px] overflow-y-auto border">

          {messages.length === 0 && (
            <p className="text-gray-500">
              שאל שאלה על הקורס בעברית או באנגלית.
            </p>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={`mb-4 ${
                m.role === "user" ? "text-right" : "text-left"
              }`}
            >
              <div
                className={`inline-block px-4 py-3 rounded-xl ${
                  m.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-200"
                }`}
              >
                <ReactMarkdown>{m.content}</ReactMarkdown>
              </div>

              {m.sources && m.sources.length > 0 && (
                <div className="text-xs mt-2 text-gray-500">
                  מקורות: {m.sources.length}
                </div>
              )}
            </div>
          ))}

          <div ref={bottomRef}></div>

        </div>

        <div className="flex gap-2 mt-4">

          <input
            className="flex-1 border rounded-lg px-4 py-3"
            placeholder="שאל שאלה..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") sendMessage()
            }}
          />

          <button
            onClick={sendMessage}
            disabled={sending}
            className="bg-blue-600 text-white px-6 py-3 rounded-lg"
          >
            {sending ? "חושב..." : "שלח"}
          </button>

        </div>

      </div>
    </div>
  )
}
