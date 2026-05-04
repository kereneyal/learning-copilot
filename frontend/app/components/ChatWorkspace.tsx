"use client"

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
} from "react"
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
  type?: string
  title?: string
  course_id?: string
  course_name?: string
  lecture_id?: string
  lecture_title?: string
  document_id?: string
  document_name?: string
  snippet?: string
  chunk_index?: number
}

type MultipleChoiceReply = {
  correct_letter: string
  explanation: string
}

/** Parsed MC from /questions/extract-from-image (for draft / future UI). */
type ExtractedMcDraft = {
  qa_mode: string
  parsed_multiple_choice: {
    stem?: string
    option_script?: string
    options?: { letter: string; text: string }[]
    retrieval_query?: string
  } | null
}

const QUESTION_IMAGE_ACCEPT = "image/png,image/jpeg,image/jpg,image/webp"
const QUESTION_IMAGE_EXTENSIONS = /\.(png|jpe?g|webp)$/i

function isAllowedPasteImageMime(mime: string): boolean {
  const t = mime.toLowerCase().split(";")[0].trim()
  return (
    t === "image/png" ||
    t === "image/jpeg" ||
    t === "image/jpg" ||
    t === "image/pjpeg" ||
    t === "image/webp"
  )
}

function extensionForImageMime(mime: string): string {
  const t = mime.toLowerCase().split(";")[0].trim()
  if (t === "image/png") return ".png"
  if (t === "image/webp") return ".webp"
  return ".jpg"
}

type Message = {
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  /** Search-intent only: inline list under the answer. QA uses sources panel only. */
  search_results?: Source[]
  showInlineResults?: boolean
  mode?: string
  qa_mode?: string
  multiple_choice?: MultipleChoiceReply | null
}

type AssistantTab = "chat" | "exam"

type ExamSimulationQuestion = {
  simulation_question_id: string
  question_id: string
  topic: string
  difficulty: string
  question_type: string
  question_text: string
  options?: string[]
}

type ExamSimulationResponse = {
  simulation_id: string
  question_count: number
  questions: ExamSimulationQuestion[]
}

type ExamSimulationResult = {
  score: number
  max_score: number
  percentage: number
  weak_topics: string[]
}

function MultipleChoiceAnswerBlock({
  mc,
  fallbackContent,
}: {
  mc: MultipleChoiceReply
  fallbackContent: string
}) {
  const isUnknown = mc.correct_letter === "UNKNOWN"

  const badgeClassName = isUnknown
    ? "rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-center"
    : "rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-center"
  const headingClassName = isUnknown
    ? "text-xs font-medium uppercase tracking-wide text-slate-500"
    : "text-xs font-medium uppercase tracking-wide text-emerald-700"
  const letterClassName = isUnknown
    ? "mt-1 text-3xl font-bold text-slate-800 tabular-nums"
    : "mt-1 text-3xl font-bold text-emerald-900 tabular-nums"
  const helperClassName = "mt-2 text-xs font-medium text-emerald-800/90"

  return (
    <div className="space-y-4">
      <div className={badgeClassName}>
        <div className={headingClassName}>תשובה נבחרת</div>
        <div className={letterClassName} dir="auto">
          {isUnknown ? "לא נכרע" : mc.correct_letter}
        </div>
        {!isUnknown && (
          <p className={helperClassName}>תשובה נכונה לפי החומר</p>
        )}
      </div>
      <div className="prose prose-sm max-w-none text-slate-900">
        <ReactMarkdown>{mc.explanation || fallbackContent}</ReactMarkdown>
      </div>
    </div>
  )
}

export default function ChatWorkspace() {
  const [assistantTab, setAssistantTab] = useState<AssistantTab>("chat")

  const [courses, setCourses] = useState<Course[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")
  const [chatMode, setChatMode] = useState<"auto" | "global" | "course" | "lecture">("auto")
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState("")
  const [loadError, setLoadError] = useState("")
  const [imageExtractError, setImageExtractError] = useState("")
  const [imageExtractSuccessHint, setImageExtractSuccessHint] = useState("")
  const [imageExtracting, setImageExtracting] = useState(false)
  const [draftExtractedMc, setDraftExtractedMc] = useState<ExtractedMcDraft | null>(null)
  const questionImageInputRef = useRef<HTMLInputElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const [examLoading, setExamLoading] = useState(false)
  const [examSubmitting, setExamSubmitting] = useState(false)
  const [examError, setExamError] = useState("")
  const [examSimulationId, setExamSimulationId] = useState("")
  const [examQuestions, setExamQuestions] = useState<ExamSimulationQuestion[]>([])
  const [examCurrentIndex, setExamCurrentIndex] = useState(0)
  const [examSelectedAnswer, setExamSelectedAnswer] = useState<number | null>(null)
  const [examFeedback, setExamFeedback] = useState("")
  const [examAnswered, setExamAnswered] = useState(false)
  const [examResult, setExamResult] = useState<ExamSimulationResult | null>(null)

  const [examConfig, setExamConfig] = useState({
    question_count: 10,
    topic: "",
    difficulty: "mixed",
    language: "he",
  })

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

  const currentExamQuestion = useMemo(
    () => examQuestions[examCurrentIndex] || null,
    [examQuestions, examCurrentIndex]
  )

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

  function extractList<T>(body: unknown): T[] {
    if (Array.isArray(body)) return body as T[]
    if (body !== null && typeof body === "object") {
      const b = body as Record<string, unknown>
      if (Array.isArray(b.data)) return b.data as T[]
      if (b.data !== null && typeof b.data === "object") {
        const d = b.data as Record<string, unknown>
        if (Array.isArray(d.items)) return d.items as T[]
      }
    }
    return []
  }

  async function fetchCourses() {
    try {
      const res = await fetch(`${API_BASE}/courses/`)
      if (!res.ok) {
        const text = await res.text().catch(() => "")
        console.error(`fetchCourses: HTTP ${res.status}`, text)
        setLoadError("שגיאה בטעינת קורסים")
        return
      }
      const body = await res.json()
      const list = extractList<Course>(body)
      setCourses(list)
      if (list.length > 0 && !selectedCourseId) {
        setSelectedCourseId(list[0].id)
      }
    } catch (err) {
      console.error("fetchCourses:", err)
      setLoadError("שגיאת רשת — לא ניתן לטעון קורסים. בדוק ש-NEXT_PUBLIC_API_BASE_URL נכון ושהשרת פועל.")
    }
  }

  async function fetchLectures(courseId: string) {
    try {
      const res = await fetch(`${API_BASE}/lectures/course/${courseId}`)
      if (!res.ok) {
        const text = await res.text().catch(() => "")
        console.error(`fetchLectures: HTTP ${res.status}`, text)
        setLectures([])
        return
      }
      const body = await res.json()
      setLectures(extractList<Lecture>(body))
    } catch (err) {
      console.error("fetchLectures:", err)
      setLectures([])
    }
  }

  function getSourceTypeLabel(type?: string) {
    switch (type) {
      case "course":
        return "קורס"
      case "lecture":
        return "הרצאה"
      case "document":
        return "מסמך"
      case "summary":
        return "סיכום"
      case "chunk":
        return "קטע"
      default:
        return "מקור"
    }
  }

  function buildKnowledgeUrl(item: Source) {
    const params = new URLSearchParams()

    if (item.course_id) {
      params.set("courseId", item.course_id)
    }
    if (item.lecture_id) {
      params.set("lectureId", item.lecture_id)
      params.set("tab", "documents")
    }
    if (item.document_id) {
      params.set("documentId", item.document_id)
      params.set("tab", "documents")
    }

    const qs = params.toString()
    return qs ? `/knowledge?${qs}` : "/knowledge"
  }

  async function sendMessage() {
    if (!input.trim() || sending) return

    const userText = input
    setMessages((prev) => [...prev, { role: "user", content: userText }])
    setInput("")
    setDraftExtractedMc(null)
    setSending(true)
    setError("")
    setImageExtractError("")
    setImageExtractSuccessHint("")

    try {
      const body: any = {
        question: userText,
        mode: chatMode,
      }

      // Course context from the UI: always send when a course is selected, except explicit global mode.
      // Lets the backend use lexical + hybrid retrieval in "auto" without relying on question-only resolution.
      if (selectedCourseId && chatMode !== "global") {
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
          search_results: data.search_results || [],
          showInlineResults: data.show_inline_results === true,
          mode: data.mode,
          qa_mode: data.qa_mode,
          multiple_choice: data.multiple_choice ?? null,
        },
      ])
    } catch {
      setError("שגיאה בקבלת תשובת הסוכן")
    } finally {
      setSending(false)
    }
  }

  function openQuestionImagePicker() {
    setImageExtractError("")
    setImageExtractSuccessHint("")
    questionImageInputRef.current?.click()
  }

  async function extractQuestionImageFromFile(
    file: File,
    source: "file" | "paste"
  ) {
    setImageExtractError("")
    setImageExtractSuccessHint("")
    setImageExtracting(true)
    try {
      const fd = new FormData()
      fd.append("file", file)

      const res = await fetch(`${API_BASE}/questions/extract-from-image`, {
        method: "POST",
        body: fd,
      })

      const data = await res.json().catch(() => ({}))

      if (!res.ok) {
        if (source === "paste") {
          setImageExtractError("לא הצלחנו לזהות טקסט מהתמונה")
        } else {
          let detailMsg =
            "לא ניתן לחלץ טקסט מהתמונה. נסה תמונה אחרת או בדוק את חיבור השרת."
          const d = data?.detail
          if (typeof d === "string") detailMsg = d
          else if (Array.isArray(d))
            detailMsg = d.map((x: unknown) => String(x)).join(" ")
          setImageExtractError(detailMsg)
        }
        return
      }

      const normalized =
        typeof data.normalized_text === "string" ? data.normalized_text : ""
      if (!normalized.trim()) {
        setImageExtractError(
          source === "paste"
            ? "לא הצלחנו לזהות טקסט מהתמונה"
            : "לא זוהה טקסט בתמונה. נסה צילום חד יותר."
        )
        return
      }

      setInput(normalized)
      setDraftExtractedMc({
        qa_mode: data.qa_mode === "multiple_choice" ? "multiple_choice" : "open",
        parsed_multiple_choice:
          data.parsed_multiple_choice && typeof data.parsed_multiple_choice === "object"
            ? data.parsed_multiple_choice
            : null,
      })
      setImageExtractSuccessHint("השאלה זוהתה מהתמונה")
    } catch {
      setImageExtractError(
        source === "paste"
          ? "לא הצלחנו לזהות טקסט מהתמונה"
          : "שגיאת רשת בזמן העלאת התמונה. נסה שוב."
      )
    } finally {
      setImageExtracting(false)
    }
  }

  async function onQuestionImageSelected(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return

    if (!QUESTION_IMAGE_EXTENSIONS.test(file.name)) {
      setImageExtractError("נא להעלות תמונה מסוג PNG, JPG או WebP בלבד.")
      return
    }

    await extractQuestionImageFromFile(file, "file")
  }

  function onChatInputPaste(e: ClipboardEvent<HTMLInputElement>) {
    if (imageExtracting || sending) return

    const items = e.clipboardData?.items
    if (!items?.length) return

    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      if (item.kind !== "file") continue
      const mime = item.type || ""
      if (!mime.startsWith("image/")) continue
      if (!isAllowedPasteImageMime(mime)) continue

      const blob = item.getAsFile()
      if (!blob || blob.size === 0) continue

      e.preventDefault()
      const name = blob.name?.trim()
        ? blob.name
        : `pasted-image${extensionForImageMime(mime)}`
      const file = new File([blob], name, { type: blob.type || mime })
      void extractQuestionImageFromFile(file, "paste")
      return
    }
  }

  async function startExamSimulation() {
    try {
      setExamLoading(true)
      setExamError("")
      setExamFeedback("")
      setExamResult(null)
      setExamSelectedAnswer(null)
      setExamAnswered(false)

      const payload = {
        mode: examConfig.topic ? "topic" : "full",
        topic: examConfig.topic || null,
        difficulty: examConfig.difficulty,
        question_count: Number(examConfig.question_count || 10),
        language: examConfig.language || "he",
        include_course_material: true,
        include_public_bank: true,
      }

      const res = await fetch(`${API_BASE}/exam/simulations/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        throw new Error("Failed to generate exam simulation")
      }

      const data: ExamSimulationResponse = await res.json()
      setExamSimulationId(data.simulation_id)
      setExamQuestions(data.questions || [])
      setExamCurrentIndex(0)
      setExamSelectedAnswer(null)
      setExamAnswered(false)
      setExamFeedback("")
      setExamResult(null)
    } catch (err) {
      console.error(err)
      setExamError("שגיאה ביצירת סימולציה")
    } finally {
      setExamLoading(false)
    }
  }

  async function submitExamAnswer() {
    try {
      if (!examSimulationId || !currentExamQuestion) return
      if (examSelectedAnswer === null) {
        setExamError("יש לבחור תשובה")
        return
      }

      setExamSubmitting(true)
      setExamError("")

      const res = await fetch(`${API_BASE}/exam/simulations/${examSimulationId}/answer`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          simulation_question_id: currentExamQuestion.simulation_question_id,
          user_answer_index: examSelectedAnswer,
        }),
      })

      if (!res.ok) {
        throw new Error("Failed to submit answer")
      }

      const data = await res.json()

      setExamFeedback(
        `${data.is_correct ? "✅ נכון" : "❌ לא נכון"}\n\n` +
          `התשובה הנכונה: ${data.correct_answer_text || ""}\n\n` +
          `${data.explanation || ""}`
      )
      setExamAnswered(true)
    } catch (err) {
      console.error(err)
      setExamError("שגיאה בשליחת תשובה")
    } finally {
      setExamSubmitting(false)
    }
  }

  async function finishExamSimulation() {
    try {
      if (!examSimulationId) return

      const res = await fetch(`${API_BASE}/exam/simulations/${examSimulationId}/finish`, {
        method: "POST",
      })

      if (!res.ok) {
        throw new Error("Failed to finish simulation")
      }

      const data: ExamSimulationResult = await res.json()
      setExamResult(data)
    } catch (err) {
      console.error(err)
      setExamError("שגיאה בסיום הסימולציה")
    }
  }

  function nextExamQuestion() {
    if (examCurrentIndex < examQuestions.length - 1) {
      setExamCurrentIndex((prev) => prev + 1)
      setExamSelectedAnswer(null)
      setExamFeedback("")
      setExamAnswered(false)
      return
    }

    finishExamSimulation()
  }

  function resetExamSimulation() {
    setExamSimulationId("")
    setExamQuestions([])
    setExamCurrentIndex(0)
    setExamSelectedAnswer(null)
    setExamFeedback("")
    setExamAnswered(false)
    setExamResult(null)
    setExamError("")
  }

  function AssistantModeTabs() {
    return (
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => setAssistantTab("chat")}
          className={`rounded-xl px-4 py-2 text-sm font-medium ${
            assistantTab === "chat" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"
          }`}
        >
          שיחה
        </button>
        <button
          onClick={() => setAssistantTab("exam")}
          className={`rounded-xl px-4 py-2 text-sm font-medium ${
            assistantTab === "exam" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-700"
          }`}
        >
          סימולציית מבחן
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {loadError && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-amber-800 text-sm">
          {loadError}
        </div>
      )}
      <CourseContextBar
        selectedCourse={selectedCourse}
        selectedLecture={selectedLecture}
        chatMode={chatMode}
        setChatMode={setChatMode}
      />

      {error && assistantTab === "chat" && (
        <div className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-red-700">
          {error}
        </div>
      )}

      {examError && assistantTab === "exam" && (
        <div className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-red-700">
          {examError}
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        <section className="col-span-12 xl:col-span-8 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <AssistantModeTabs />

          {assistantTab === "chat" && (
            <>
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
                      <li>איפה דיברו על דירקטוריון?</li>
                    </ul>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {messages.map((m, i) => (
                      <div key={i} className={`flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
                        <div
                          className={`max-w-[90%] rounded-2xl px-4 py-3 shadow-sm ${
                            m.role === "user"
                              ? "bg-blue-600 text-white"
                              : "border border-slate-200 bg-white text-slate-900"
                          }`}
                        >
                          <div className="mb-2 text-xs font-semibold opacity-70">
                            {m.role === "user" ? "אתה" : `הסוכן${m.mode ? ` • ${m.mode}` : ""}`}
                          </div>

                          <div
                            className={
                              m.role === "user"
                                ? "prose prose-sm max-w-none prose-invert"
                                : m.qa_mode === "multiple_choice" && m.multiple_choice
                                  ? "not-prose max-w-none"
                                  : "prose prose-sm max-w-none text-slate-900"
                            }
                          >
                            {m.role === "assistant" &&
                            m.qa_mode === "multiple_choice" &&
                            m.multiple_choice ? (
                              <MultipleChoiceAnswerBlock
                                mc={m.multiple_choice}
                                fallbackContent={m.content}
                              />
                            ) : (
                              <ReactMarkdown>{m.content}</ReactMarkdown>
                            )}
                          </div>

                          {m.role === "assistant" &&
                            m.showInlineResults === true &&
                            !!m.search_results?.length && (
                            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-3">
                              <div className="mb-3 text-sm font-semibold text-slate-700">
                                נמצאו תוצאות רלוונטיות
                              </div>

                              <div className="space-y-2">
                                {m.search_results.slice(0, 6).map((item, idx) => (
                                  <a
                                    key={`${item.type}-${item.document_id || "no-doc"}-${item.lecture_id || "no-lecture"}-${item.chunk_index ?? idx}`}
                                    href={buildKnowledgeUrl(item)}
                                    className="block rounded-xl border border-slate-200 bg-white p-3 transition hover:bg-slate-50"
                                  >
                                    <div className="mb-1 flex items-center justify-between gap-3">
                                      <div className="text-sm font-medium text-slate-900">
                                        {item.lecture_title || item.document_name || item.title || "תוצאה"}
                                      </div>
                                      <span className="rounded-full bg-indigo-100 px-2 py-1 text-xs text-indigo-700">
                                        {getSourceTypeLabel(item.type)}
                                      </span>
                                    </div>

                                    {!!item.snippet && (
                                      <div className="text-sm text-slate-600">
                                        {item.snippet}
                                      </div>
                                    )}
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                    <div ref={bottomRef} />
                  </div>
                )}
              </div>

              {imageExtractError && (
                <div
                  className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
                  role="alert"
                >
                  {imageExtractError}
                </div>
              )}

              {imageExtractSuccessHint && !imageExtractError && (
                <div className="mt-2 text-sm text-emerald-700" role="status">
                  {imageExtractSuccessHint}
                </div>
              )}

              {draftExtractedMc?.qa_mode === "multiple_choice" && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full bg-violet-100 px-2.5 py-0.5 text-xs font-medium text-violet-800">
                    זוהתה שאלה אמריקאית
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setDraftExtractedMc(null)
                      setImageExtractSuccessHint("")
                    }}
                    className="text-xs text-slate-500 underline hover:text-slate-700"
                  >
                    הסר סימון
                  </button>
                </div>
              )}

              <div className="mt-2 flex gap-2">
                <input
                  ref={questionImageInputRef}
                  type="file"
                  accept={QUESTION_IMAGE_ACCEPT}
                  className="hidden"
                  onChange={onQuestionImageSelected}
                />
                <input
                  className="flex-1 rounded-xl border px-4 py-3"
                  placeholder="שאל שאלה על הידע שבמערכת..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onPaste={onChatInputPaste}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") sendMessage()
                  }}
                />
                <button
                  type="button"
                  title="העלאת תמונת שאלה (חילוץ טקסט)"
                  onClick={openQuestionImagePicker}
                  disabled={imageExtracting || sending}
                  className="shrink-0 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {imageExtracting ? "מחלץ…" : "תמונה"}
                </button>
                <button
                  onClick={sendMessage}
                  disabled={sending}
                  className="rounded-xl bg-blue-600 px-5 py-3 font-medium text-white disabled:opacity-50"
                >
                  {sending ? "חושב..." : "שלח"}
                </button>
              </div>
            </>
          )}

          {assistantTab === "exam" && (
            <div className="space-y-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-lg font-semibold">סימולציית מבחן דירקטורים</h3>
                <div className="text-sm text-slate-500">
                  תרגול רב-ברירה עם בדיקה מיידית
                </div>
              </div>

              {!examSimulationId && !examResult && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                    <input
                      type="number"
                      min={1}
                      max={100}
                      className="rounded-xl border px-3 py-2"
                      value={examConfig.question_count}
                      onChange={(e) =>
                        setExamConfig((p) => ({
                          ...p,
                          question_count: Number(e.target.value || 10),
                        }))
                      }
                      placeholder="מספר שאלות"
                    />

                    <select
                      className="rounded-xl border px-3 py-2"
                      value={examConfig.topic}
                      onChange={(e) =>
                        setExamConfig((p) => ({ ...p, topic: e.target.value }))
                      }
                    >
                      <option value="">כל הנושאים</option>
                      <option value="governance">governance</option>
                      <option value="board_responsibilities">board_responsibilities</option>
                      <option value="audit_committee">audit_committee</option>
                      <option value="financial_statements">financial_statements</option>
                      <option value="risk_management">risk_management</option>
                      <option value="strategy">strategy</option>
                      <option value="corporate_law">corporate_law</option>
                      <option value="conflict_of_interest">conflict_of_interest</option>
                    </select>

                    <select
                      className="rounded-xl border px-3 py-2"
                      value={examConfig.difficulty}
                      onChange={(e) =>
                        setExamConfig((p) => ({ ...p, difficulty: e.target.value }))
                      }
                    >
                      <option value="mixed">mixed</option>
                      <option value="easy">easy</option>
                      <option value="medium">medium</option>
                      <option value="hard">hard</option>
                      <option value="case">case</option>
                    </select>

                    <button
                      onClick={startExamSimulation}
                      disabled={examLoading}
                      className="rounded-xl bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"
                    >
                      {examLoading ? "יוצר..." : "התחל סימולציה"}
                    </button>
                  </div>

                  <div className="rounded-2xl border bg-slate-50 p-4 text-sm text-slate-600">
                    אפשר לבחור מספר שאלות, נושא ורמת קושי, ואז להתחיל סימולציה.
                  </div>
                </div>
              )}

              {examSimulationId && !examResult && currentExamQuestion && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
                    <div className="text-sm text-slate-500">
                      שאלה {examCurrentIndex + 1} מתוך {examQuestions.length}
                    </div>
                    <div className="text-sm text-slate-500">
                      {currentExamQuestion.topic} • {currentExamQuestion.difficulty}
                    </div>
                  </div>

                  <div className="rounded-2xl border p-4">
                    <div className="mb-4 text-lg font-medium">
                      {currentExamQuestion.question_text}
                    </div>

                    <div className="space-y-2">
                      {(currentExamQuestion.options || []).map((option, idx) => (
                        <label
                          key={idx}
                          className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 ${
                            examSelectedAnswer === idx ? "border-emerald-500 bg-emerald-50" : "border-slate-200"
                          }`}
                        >
                          <input
                            type="radio"
                            name="exam_answer"
                            checked={examSelectedAnswer === idx}
                            onChange={() => setExamSelectedAnswer(idx)}
                          />
                          <span>{option}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {!examAnswered ? (
                      <button
                        onClick={submitExamAnswer}
                        disabled={examSubmitting}
                        className="rounded-xl bg-indigo-600 px-4 py-2 text-white disabled:opacity-50"
                      >
                        {examSubmitting ? "שולח..." : "שלח תשובה"}
                      </button>
                    ) : (
                      <button
                        onClick={nextExamQuestion}
                        className="rounded-xl bg-emerald-600 px-4 py-2 text-white"
                      >
                        {examCurrentIndex === examQuestions.length - 1 ? "סיים מבחן" : "לשאלה הבאה"}
                      </button>
                    )}

                    <button
                      onClick={resetExamSimulation}
                      className="rounded-xl bg-slate-100 px-4 py-2"
                    >
                      אתחל
                    </button>
                  </div>

                  <div className="rounded-2xl border bg-slate-50 p-4 whitespace-pre-wrap text-sm">
                    {examFeedback || "בחר תשובה ושלח."}
                  </div>
                </div>
              )}

              {examResult && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <div className="rounded-2xl border bg-slate-50 p-4">
                      <div className="text-sm text-slate-500">ציון</div>
                      <div className="mt-1 text-2xl font-semibold">
                        {examResult.score} / {examResult.max_score}
                      </div>
                    </div>
                    <div className="rounded-2xl border bg-slate-50 p-4">
                      <div className="text-sm text-slate-500">אחוז הצלחה</div>
                      <div className="mt-1 text-2xl font-semibold">{examResult.percentage}%</div>
                    </div>
                    <div className="rounded-2xl border bg-slate-50 p-4">
                      <div className="text-sm text-slate-500">נושאים חלשים</div>
                      <div className="mt-1 text-sm font-medium">
                        {examResult.weak_topics?.length ? examResult.weak_topics.join(", ") : "אין"}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={resetExamSimulation}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-white"
                  >
                    סימולציה חדשה
                  </button>
                </div>
              )}
            </div>
          )}
        </section>

        <div className="col-span-12 xl:col-span-4">
          {assistantTab === "chat" ? (
            <SourcePanel sources={latestAssistantSources} />
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-3 text-lg font-semibold">הכוונה</div>
              <div className="space-y-2 text-sm text-slate-600">
                <p>• בחר מספר שאלות שמתאים לך.</p>
                <p>• אפשר לבחור נושא מסוים או להשאיר מעורב.</p>
                <p>• לאחר כל תשובה תראה אם צדקת ומה ההסבר.</p>
                <p>• בסיום תקבל ציון ונושאים חלשים.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
