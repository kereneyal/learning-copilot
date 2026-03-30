"use client"

import { useEffect, useMemo, useState } from "react"
import Toast from "../components/Toast"
import LoadingSkeleton from "../components/LoadingSkeleton"
import EmptyState from "../components/EmptyState"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"

type Course = {
  id: string
  name: string
  institution?: string
  semester?: string
  default_language?: string
}

type Lecturer = {
  id: string
  full_name: string
  bio?: string
}

type Lecture = {
  id: string
  course_id: string
  lecturer_id: string | null
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
  processing_status?: string
  last_error?: string
}

type DocumentDetails = {
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
  processing_status?: string
  last_error?: string
  has_summary?: boolean
  summary_text?: string
  raw_text_preview?: string
  raw_text_length?: number
}

type SyllabusPreviewResponse = {
  file_name?: string
  file_path?: string
  raw_text?: string
  text_preview?: string
  parsed?: {
    course_name?: string
    institution?: string
    semester?: string
    language?: string
    lecturers?: Array<{
      full_name: string
      bio?: string | null
    }>
    lectures?: Array<{
      title: string
      lecture_date?: string | null
      lecturer_name?: string | null
      notes?: string | null
    }>
  }
}

type ToastState = {
  message: string
  type: "info" | "success" | "error"
} | null

type TabKey = "courses" | "documents" | "processing" | "syllabus"
type QuickFilter = "all" | "failed" | "processing" | "no_summary" | "selected_lecture"

const PAGE_SIZE = 10
const STORAGE_KEY = "knowledge_center_saved_view_v1"

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState<TabKey>("documents")

  const [courses, setCourses] = useState<Course[]>([])
  const [lecturers, setLecturers] = useState<Lecturer[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [documents, setDocuments] = useState<CourseDocument[]>([])

  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")

  const [loading, setLoading] = useState(false)
  const [uploadingBatch, setUploadingBatch] = useState(false)
  const [toast, setToast] = useState<ToastState>(null)

  const [documentDetails, setDocumentDetails] = useState<DocumentDetails | null>(null)
  const [loadingDocumentDetails, setLoadingDocumentDetails] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])

  const [searchTerm, setSearchTerm] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [languageFilter, setLanguageFilter] = useState("all")
  const [sourceTypeFilter, setSourceTypeFilter] = useState("all")
  const [lectureFilter, setLectureFilter] = useState("all")
  const [sortBy, setSortBy] = useState("file_name")
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all")

  const [currentPage, setCurrentPage] = useState(1)

  const [newCourse, setNewCourse] = useState({
    name: "",
    institution: "",
    default_language: "en",
    semester: "",
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
    lecture_id: "",
    files: [] as File[],
  })

  const [syllabusFile, setSyllabusFile] = useState<File | null>(null)
  const [syllabusPreview, setSyllabusPreview] = useState<SyllabusPreviewResponse | null>(null)
  const [previewingSyllabus, setPreviewingSyllabus] = useState(false)
  const [creatingFromSyllabus, setCreatingFromSyllabus] = useState(false)

  const selectedCourse = useMemo(
    () => courses.find((c) => c.id === selectedCourseId) || null,
    [courses, selectedCourseId]
  )

  const selectedLecture = useMemo(
    () => lectures.find((l) => l.id === selectedLectureId) || null,
    [lectures, selectedLectureId]
  )

  const hasProcessingDocuments = useMemo(
    () => documents.some((d) => d.processing_status === "processing"),
    [documents]
  )

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      try {
        const saved = JSON.parse(raw)
        setStatusFilter(saved.statusFilter || "all")
        setLanguageFilter(saved.languageFilter || "all")
        setSourceTypeFilter(saved.sourceTypeFilter || "all")
        setSortBy(saved.sortBy || "file_name")
        setQuickFilter(saved.quickFilter || "all")
      } catch {}
    }
    fetchCourses()
    fetchLecturers()
  }, [])

  useEffect(() => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        statusFilter,
        languageFilter,
        sourceTypeFilter,
        sortBy,
        quickFilter,
      })
    )
  }, [statusFilter, languageFilter, sourceTypeFilter, sortBy, quickFilter])

  useEffect(() => {
    if (selectedCourseId) {
      fetchLectures(selectedCourseId)
      fetchDocumentsByCourse(selectedCourseId)
      setSelectedLectureId("")
      setUploadForm((p) => ({ ...p, lecture_id: "" }))
      setLectureFilter("all")
      setCurrentPage(1)
    } else {
      setLectures([])
      setDocuments([])
      setSelectedLectureId("")
      setUploadForm((p) => ({ ...p, lecture_id: "" }))
      setLectureFilter("all")
      setCurrentPage(1)
    }
  }, [selectedCourseId])

  useEffect(() => {
    if (selectedLectureId) {
      fetchDocumentsByLecture(selectedLectureId)
      setUploadForm((p) => ({ ...p, lecture_id: selectedLectureId }))
      setCurrentPage(1)
    }
  }, [selectedLectureId])

  useEffect(() => {
    setCurrentPage(1)
  }, [searchTerm, statusFilter, languageFilter, sourceTypeFilter, lectureFilter, sortBy, quickFilter])

  useEffect(() => {
    if (!hasProcessingDocuments) return

    const interval = setInterval(() => {
      if (selectedLectureId) {
        fetchDocumentsByLecture(selectedLectureId, false)
      } else if (selectedCourseId) {
        fetchDocumentsByCourse(selectedCourseId, false)
      }
    }, 4000)

    return () => clearInterval(interval)
  }, [hasProcessingDocuments, selectedLectureId, selectedCourseId])

  async function fetchCourses() {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/courses/`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setCourses(data)
      if (data.length > 0 && !selectedCourseId) {
        setSelectedCourseId(data[0].id)
      }
    } catch {
      setToast({ message: "שגיאה בטעינת קורסים", type: "error" })
    } finally {
      setLoading(false)
    }
  }

  async function fetchLecturers() {
    try {
      const res = await fetch(`${API_BASE}/lecturers/`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setLecturers(data)
    } catch {
      setToast({ message: "שגיאה בטעינת מרצים", type: "error" })
    }
  }

  async function fetchLectures(courseId: string) {
    try {
      const res = await fetch(`${API_BASE}/lectures/course/${courseId}`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setLectures(data)
    } catch {
      setToast({ message: "שגיאה בטעינת הרצאות", type: "error" })
    }
  }

  async function fetchDocumentsByCourse(courseId: string, showErrorToast = true) {
    try {
      const res = await fetch(`${API_BASE}/documents/course/${courseId}`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setDocuments(data)
      setSelectedDocumentIds([])
    } catch {
      if (showErrorToast) setToast({ message: "שגיאה בטעינת מסמכים", type: "error" })
    }
  }

  async function fetchDocumentsByLecture(lectureId: string, showErrorToast = true) {
    try {
      const res = await fetch(`${API_BASE}/documents/lecture/${lectureId}`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setDocuments(data)
      setSelectedDocumentIds([])
    } catch {
      if (showErrorToast) setToast({ message: "שגיאה בטעינת מסמכי הרצאה", type: "error" })
    }
  }

  async function fetchDocumentDetails(documentId: string) {
    try {
      setLoadingDocumentDetails(true)
      setDrawerOpen(true)
      const res = await fetch(`${API_BASE}/documents/${documentId}`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setDocumentDetails(data)
    } catch {
      setToast({ message: "שגיאה בטעינת פרטי המסמך", type: "error" })
    } finally {
      setLoadingDocumentDetails(false)
    }
  }

  async function retryDocumentProcessing(documentId: string) {
    try {
      const res = await fetch(`${API_BASE}/documents/${documentId}/retry-processing`, {
        method: "POST",
      })
      if (!res.ok) throw new Error()

      setToast({ message: "בוצע ניסיון עיבוד מחדש למסמך", type: "success" })

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else if (selectedCourseId) {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      await fetchDocumentDetails(documentId)
    } catch {
      setToast({ message: "שגיאה בניסיון עיבוד מחדש", type: "error" })
    }
  }

  async function deleteDocument(documentId: string) {
    if (!window.confirm("למחוק את המסמך?")) return
    try {
      const res = await fetch(`${API_BASE}/documents/${documentId}`, { method: "DELETE" })
      if (!res.ok) throw new Error()

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else if (selectedCourseId) {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setSelectedDocumentIds((prev) => prev.filter((id) => id !== documentId))
      if (documentDetails?.id === documentId) {
        setDrawerOpen(false)
        setDocumentDetails(null)
      }
      setToast({ message: "המסמך נמחק בהצלחה", type: "success" })
    } catch {
      setToast({ message: "שגיאה במחיקת מסמך", type: "error" })
    }
  }

  async function bulkDeleteDocuments() {
    if (selectedDocumentIds.length === 0) {
      setToast({ message: "לא נבחרו מסמכים", type: "error" })
      return
    }

    if (!window.confirm(`למחוק ${selectedDocumentIds.length} מסמכים?`)) return

    try {
      await Promise.all(
        selectedDocumentIds.map((id) =>
          fetch(`${API_BASE}/documents/${id}`, { method: "DELETE" })
        )
      )

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else if (selectedCourseId) {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setSelectedDocumentIds([])
      setToast({ message: "המסמכים נמחקו", type: "success" })
    } catch {
      setToast({ message: "שגיאה במחיקת מסמכים", type: "error" })
    }
  }

  async function bulkRetryFailed() {
    const failedIds = filteredDocuments
      .filter((d) => selectedDocumentIds.includes(d.id))
      .filter((d) => d.processing_status === "failed")
      .map((d) => d.id)

    if (failedIds.length === 0) {
      setToast({ message: "אין מסמכים נכשלים מסומנים", type: "error" })
      return
    }

    try {
      await Promise.all(
        failedIds.map((id) =>
          fetch(`${API_BASE}/documents/${id}/retry-processing`, { method: "POST" })
        )
      )

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else if (selectedCourseId) {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setToast({ message: "בוצע ניסיון עיבוד מחדש למסמכים שנבחרו", type: "success" })
    } catch {
      setToast({ message: "שגיאה בעיבוד מחדש קבוצתי", type: "error" })
    }
  }

  async function previewSyllabus() {
    try {
      if (!syllabusFile) {
        setToast({ message: "יש לבחור קובץ סילבוס", type: "error" })
        return
      }

      setPreviewingSyllabus(true)
      const formData = new FormData()
      formData.append("file", syllabusFile)

      const res = await fetch(`${API_BASE}/syllabus/preview`, {
        method: "POST",
        body: formData,
      })

      if (!res.ok) throw new Error()
      const data = await res.json()
      setSyllabusPreview(data)
      setToast({ message: "הסילבוס נותח בהצלחה", type: "success" })
    } catch {
      setToast({ message: "שגיאה בניתוח הסילבוס", type: "error" })
    } finally {
      setPreviewingSyllabus(false)
    }
  }

  async function createCourseFromSyllabus() {
    try {
      if (!syllabusPreview?.parsed) {
        setToast({ message: "אין preview מוכן", type: "error" })
        return
      }

      setCreatingFromSyllabus(true)
      const payload = {
        course_name: syllabusPreview.parsed.course_name || "New Course",
        institution: syllabusPreview.parsed.institution || "",
        semester: syllabusPreview.parsed.semester || "",
        language: syllabusPreview.parsed.language || "en",
        lecturers: syllabusPreview.parsed.lecturers || [],
        lectures: syllabusPreview.parsed.lectures || [],
        syllabus_file_name: syllabusPreview.file_name,
        syllabus_file_path: syllabusPreview.file_path,
        syllabus_raw_text: syllabusPreview.raw_text,
      }

      const res = await fetch(`${API_BASE}/syllabus/create-course`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!res.ok) throw new Error()
      const data = await res.json()

      await fetchCourses()
      await fetchLecturers()

      if (data?.course?.id) setSelectedCourseId(data.course.id)

      setToast({ message: "הקורס נוצר אוטומטית מהסילבוס", type: "success" })
      setSyllabusPreview(null)
      setSyllabusFile(null)
    } catch {
      setToast({ message: "שגיאה ביצירת קורס מהסילבוס", type: "error" })
    } finally {
      setCreatingFromSyllabus(false)
    }
  }

  async function createCourse() {
    try {
      const res = await fetch(`${API_BASE}/courses/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newCourse),
      })
      if (!res.ok) throw new Error()

      await fetchCourses()
      setToast({ message: "הקורס נוצר בהצלחה", type: "success" })
      setNewCourse({
        name: "",
        institution: "",
        default_language: "en",
        semester: "",
      })
    } catch {
      setToast({ message: "שגיאה ביצירת קורס", type: "error" })
    }
  }

  async function createLecturer() {
    try {
      const res = await fetch(`${API_BASE}/lecturers/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newLecturer),
      })
      if (!res.ok) throw new Error()

      await fetchLecturers()
      setToast({ message: "המרצה נוצר בהצלחה", type: "success" })
      setNewLecturer({ full_name: "", bio: "" })
    } catch {
      setToast({ message: "שגיאה ביצירת מרצה", type: "error" })
    }
  }

  async function createLecture() {
    try {
      if (!selectedCourseId) {
        setToast({ message: "יש לבחור קורס קודם", type: "error" })
        return
      }

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
      if (!res.ok) throw new Error()

      await fetchLectures(selectedCourseId)
      setToast({ message: "ההרצאה נוצרה בהצלחה", type: "success" })
      setNewLecture({
        title: "",
        lecturer_id: "",
        lecture_date: "",
        notes: "",
      })
    } catch {
      setToast({ message: "שגיאה ביצירת הרצאה", type: "error" })
    }
  }

  async function uploadFilesBatch() {
    try {
      if (!selectedCourseId) {
        setToast({ message: "יש לבחור קורס", type: "error" })
        return
      }
      if (!uploadForm.lecture_id) {
        setToast({ message: "יש לבחור הרצאה לשיוך המסמכים", type: "error" })
        return
      }
      if (uploadForm.files.length === 0) {
        setToast({ message: "יש לבחור לפחות קובץ אחד", type: "error" })
        return
      }

      setUploadingBatch(true)
      const formData = new FormData()
      formData.append("course_id", selectedCourseId)
      formData.append("lecture_id", uploadForm.lecture_id)
      formData.append("topic", uploadForm.topic)
      formData.append("source_type", uploadForm.source_type)

      for (const file of uploadForm.files) {
        formData.append("files", file)
      }

      const res = await fetch(`${API_BASE}/documents/upload-multiple`, {
        method: "POST",
        body: formData,
      })

      if (!res.ok) throw new Error()

      await fetchDocumentsByLecture(uploadForm.lecture_id)
      setSelectedLectureId(uploadForm.lecture_id)

      setToast({
        message: "הקבצים שויכו והועלו להרצאה בהצלחה",
        type: "success",
      })

      setUploadForm({
        topic: "",
        source_type: "slides",
        lecture_id: uploadForm.lecture_id,
        files: [],
      })
    } catch {
      setToast({ message: "שגיאה בהעלאת קבצים להרצאה", type: "error" })
    } finally {
      setUploadingBatch(false)
    }
  }

  const stats = useMemo(() => {
    const total = documents.length
    const ready = documents.filter((d) => (d.processing_status || "ready") === "ready").length
    const processing = documents.filter((d) => d.processing_status === "processing").length
    const failed = documents.filter((d) => d.processing_status === "failed").length
    return { total, ready, processing, failed }
  }, [documents])

  const filteredDocuments = useMemo(() => {
    const filtered = documents.filter((doc) => {
      const matchesSearch =
        !searchTerm ||
        (doc.file_name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (doc.topic || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (doc.lecture_title || "").toLowerCase().includes(searchTerm.toLowerCase())

      const matchesStatus =
        statusFilter === "all" || (doc.processing_status || "ready") === statusFilter

      const matchesLanguage =
        languageFilter === "all" || (doc.language || "unknown") === languageFilter

      const matchesSourceType =
        sourceTypeFilter === "all" || (doc.source_type || "unknown") === sourceTypeFilter

      const matchesLecture =
        lectureFilter === "all" || (doc.lecture_id || "") === lectureFilter

      const matchesQuick =
        quickFilter === "all" ||
        (quickFilter === "failed" && doc.processing_status === "failed") ||
        (quickFilter === "processing" && doc.processing_status === "processing") ||
        (quickFilter === "no_summary" && !doc.last_error && doc.processing_status === "ready") ||
        (quickFilter === "selected_lecture" && selectedLectureId && doc.lecture_id === selectedLectureId)

      return matchesSearch && matchesStatus && matchesLanguage && matchesSourceType && matchesLecture && matchesQuick
    })

    return filtered.sort((a, b) => {
      const av =
        sortBy === "status"
          ? a.processing_status || ""
          : sortBy === "language"
          ? a.language || ""
          : a.file_name || ""

      const bv =
        sortBy === "status"
          ? b.processing_status || ""
          : sortBy === "language"
          ? b.language || ""
          : b.file_name || ""

      return av.localeCompare(bv)
    })
  }, [documents, searchTerm, statusFilter, languageFilter, sourceTypeFilter, lectureFilter, sortBy, quickFilter, selectedLectureId])

  const paginatedDocuments = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE
    return filteredDocuments.slice(start, start + PAGE_SIZE)
  }, [filteredDocuments, currentPage])

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / PAGE_SIZE))

  function toggleDocumentSelection(id: string) {
    setSelectedDocumentIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  function toggleSelectAllVisible() {
    const visibleIds = paginatedDocuments.map((d) => d.id)
    const allSelected = visibleIds.every((id) => selectedDocumentIds.includes(id))

    if (allSelected) {
      setSelectedDocumentIds((prev) => prev.filter((id) => !visibleIds.includes(id)))
    } else {
      setSelectedDocumentIds((prev) => Array.from(new Set([...prev, ...visibleIds])))
    }
  }

  function renderStatusBadge(status?: string) {
    const normalized = status || "ready"
    const styles =
      normalized === "ready"
        ? "bg-emerald-100 text-emerald-700"
        : normalized === "processing"
        ? "bg-amber-100 text-amber-700"
        : normalized === "failed"
        ? "bg-red-100 text-red-700"
        : "bg-slate-100 text-slate-700"

    const label =
      normalized === "ready"
        ? "מוכן"
        : normalized === "processing"
        ? "בעיבוד"
        : normalized === "failed"
        ? "נכשל"
        : normalized

    return <span className={`rounded-full px-2 py-1 text-xs ${styles}`}>{label}</span>
  }

  function TabButton({ tab, label }: { tab: TabKey; label: string }) {
    return (
      <button
        onClick={() => setActiveTab(tab)}
        className={`rounded-xl px-4 py-2 text-sm font-medium ${
          activeTab === tab ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700"
        }`}
      >
        {label}
      </button>
    )
  }

  function KpiCard({
    label,
    value,
    color,
    onClick,
  }: {
    label: string
    value: number
    color?: string
    onClick?: () => void
  }) {
    return (
      <button
        onClick={onClick}
        className="rounded-2xl border bg-white p-4 text-right shadow-sm transition hover:shadow-md"
      >
        <div className="text-sm text-slate-500">{label}</div>
        <div className={`mt-1 text-2xl font-semibold ${color || ""}`}>{value}</div>
      </button>
    )
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold">מרכז הידע</h2>
        <p className="mt-1 text-sm text-slate-500">
          ניהול קורסים, הרצאות, מסמכים ועיבוד ידע
        </p>
      </section>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard label="סה״כ מסמכים" value={stats.total} onClick={() => setQuickFilter("all")} />
        <KpiCard label="מוכנים" value={stats.ready} color="text-emerald-700" onClick={() => setQuickFilter("all")} />
        <KpiCard label="בעיבוד" value={stats.processing} color="text-amber-700" onClick={() => setQuickFilter("processing")} />
        <KpiCard label="נכשלו" value={stats.failed} color="text-red-700" onClick={() => setQuickFilter("failed")} />
      </section>

      <section className="flex flex-wrap gap-2">
        <TabButton tab="documents" label="מסמכים" />
        <TabButton tab="processing" label="עיבוד" />
        <TabButton tab="courses" label="קורסים והרצאות" />
        <TabButton tab="syllabus" label="סילבוס" />
      </section>

      {(activeTab === "documents" || activeTab === "processing") && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <h3 className="text-lg font-semibold">
              {activeTab === "processing" ? "מסכי עיבוד" : "מסמכים"}
            </h3>
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
            <button onClick={toggleSelectAllVisible} className="rounded-xl bg-slate-100 px-4 py-2 text-sm font-medium">
              בחר / בטל בחירה של העמוד
            </button>
            <button onClick={bulkRetryFailed} className="rounded-xl bg-amber-100 px-4 py-2 text-sm font-medium text-amber-700">
              נסה שוב לנכשלים המסומנים
            </button>
            <button onClick={bulkDeleteDocuments} className="rounded-xl bg-red-100 px-4 py-2 text-sm font-medium text-red-700">
              מחק מסומנים
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

      {activeTab === "courses" && (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold">קורסים</h3>
            {loading ? (
              <LoadingSkeleton lines={4} />
            ) : courses.length === 0 ? (
              <EmptyState title="עדיין אין קורסים" description="צור את הקורס הראשון כדי להתחיל." />
            ) : (
              <div className="mb-4 max-h-[320px] space-y-2 overflow-y-auto">
                {courses.map((course) => (
                  <button
                    key={course.id}
                    onClick={() => setSelectedCourseId(course.id)}
                    className={`block w-full rounded-2xl border px-3 py-3 text-right ${
                      selectedCourseId === course.id ? "border-blue-500 bg-blue-50" : "border-slate-200"
                    }`}
                  >
                    <div className="font-medium">{course.name}</div>
                    <div className="text-xs text-slate-500">
                      {course.institution || "ללא מוסד"} • {course.semester || "ללא סמסטר"}
                    </div>
                  </button>
                ))}
              </div>
            )}

            <div className="space-y-3">
              <input className="w-full rounded-xl border px-3 py-2" placeholder="שם קורס" value={newCourse.name} onChange={(e) => setNewCourse((p) => ({ ...p, name: e.target.value }))} />
              <input className="w-full rounded-xl border px-3 py-2" placeholder="מוסד" value={newCourse.institution} onChange={(e) => setNewCourse((p) => ({ ...p, institution: e.target.value }))} />
              <input className="w-full rounded-xl border px-3 py-2" placeholder="סמסטר" value={newCourse.semester} onChange={(e) => setNewCourse((p) => ({ ...p, semester: e.target.value }))} />
              <button onClick={createCourse} className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white">
                צור קורס
              </button>
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">הרצאות</h3>
              {selectedCourse && <span className="text-sm text-slate-500">{selectedCourse.name}</span>}
            </div>

            <div className="mb-4 grid grid-cols-1 gap-3">
              <input className="rounded-xl border px-3 py-2" placeholder="כותרת הרצאה" value={newLecture.title} onChange={(e) => setNewLecture((p) => ({ ...p, title: e.target.value }))} />
              <select className="rounded-xl border px-3 py-2" value={newLecture.lecturer_id} onChange={(e) => setNewLecture((p) => ({ ...p, lecturer_id: e.target.value }))}>
                <option value="">בחר מרצה</option>
                {lecturers.map((lecturer) => (
                  <option key={lecturer.id} value={lecturer.id}>
                    {lecturer.full_name}
                  </option>
                ))}
              </select>
              <input className="rounded-xl border px-3 py-2" placeholder="תאריך הרצאה" value={newLecture.lecture_date} onChange={(e) => setNewLecture((p) => ({ ...p, lecture_date: e.target.value }))} />
              <input className="rounded-xl border px-3 py-2" placeholder="הערות" value={newLecture.notes} onChange={(e) => setNewLecture((p) => ({ ...p, notes: e.target.value }))} />
              <button onClick={createLecture} className="rounded-xl bg-purple-600 px-4 py-2 font-medium text-white">
                צור הרצאה
              </button>
            </div>

            {lectures.length === 0 ? (
              <EmptyState title="עדיין אין הרצאות" description="בחר קורס וצור הרצאות כדי להמשיך." />
            ) : (
              <div className="max-h-[320px] space-y-2 overflow-y-auto">
                {lectures.map((lecture) => (
                  <button
                    key={lecture.id}
                    onClick={() => setSelectedLectureId(lecture.id)}
                    className={`block w-full rounded-2xl border px-3 py-3 text-right ${
                      selectedLectureId === lecture.id ? "border-purple-500 bg-purple-50" : "border-slate-200"
                    }`}
                  >
                    <div className="font-medium">{lecture.title}</div>
                    <div className="text-xs text-slate-500">
                      {lecture.lecturer_name || "ללא מרצה"} • {lecture.lecture_date || "ללא תאריך"}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold">העלאת מסמכים / מרצים</h3>

            <div className="space-y-3">
              <select
                className="w-full rounded-xl border px-3 py-2"
                value={uploadForm.lecture_id}
                onChange={(e) => {
                  const value = e.target.value
                  setUploadForm((p) => ({ ...p, lecture_id: value }))
                  if (value) setSelectedLectureId(value)
                }}
              >
                <option value="">בחר הרצאה לשיוך המסמכים</option>
                {lectures.map((lecture) => (
                  <option key={lecture.id} value={lecture.id}>
                    {lecture.title}
                  </option>
                ))}
              </select>

              <input className="w-full rounded-xl border px-3 py-2" placeholder="נושא" value={uploadForm.topic} onChange={(e) => setUploadForm((p) => ({ ...p, topic: e.target.value }))} />
              <select className="w-full rounded-xl border px-3 py-2" value={uploadForm.source_type} onChange={(e) => setUploadForm((p) => ({ ...p, source_type: e.target.value }))}>
                <option value="slides">מצגת</option>
                <option value="summary">סיכום</option>
                <option value="notes">הערות</option>
                <option value="article">מאמר</option>
                <option value="syllabus">סילבוס</option>
              </select>
              <input
                className="w-full rounded-xl border px-3 py-2"
                type="file"
                multiple
                onChange={(e) =>
                  setUploadForm((p) => ({
                    ...p,
                    files: e.target.files ? Array.from(e.target.files) : [],
                  }))
                }
              />

              {uploadForm.files.length > 0 && (
                <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
                  נבחרו {uploadForm.files.length} קבצים
                </div>
              )}

              <button
                onClick={uploadFilesBatch}
                disabled={uploadingBatch}
                className="w-full rounded-xl bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-50"
              >
                {uploadingBatch ? "מעלה קבצים..." : "העלה קבצים להרצאה"}
              </button>
            </div>

            <div className="mt-6">
              <h4 className="mb-3 text-base font-semibold">הוסף מרצה</h4>
              <div className="space-y-3">
                <input className="w-full rounded-xl border px-3 py-2" placeholder="שם המרצה" value={newLecturer.full_name} onChange={(e) => setNewLecturer((p) => ({ ...p, full_name: e.target.value }))} />
                <textarea className="w-full rounded-xl border px-3 py-2" placeholder="ביוגרפיה / הערות" value={newLecturer.bio} onChange={(e) => setNewLecturer((p) => ({ ...p, bio: e.target.value }))} />
                <button onClick={createLecturer} className="w-full rounded-xl bg-slate-800 px-4 py-2 font-medium text-white">
                  צור מרצה
                </button>
              </div>
            </div>
          </section>
        </div>
      )}

      {activeTab === "syllabus" && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">צור קורס מסילבוס</h3>

          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              type="file"
              onChange={(e) => setSyllabusFile(e.target.files?.[0] || null)}
            />

            <button
              onClick={previewSyllabus}
              disabled={previewingSyllabus}
              className="rounded-xl bg-indigo-600 px-4 py-2 font-medium text-white disabled:opacity-50"
            >
              {previewingSyllabus ? "מנתח..." : "נתח סילבוס"}
            </button>
          </div>

          {syllabusPreview?.parsed && (
            <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <div><strong>קורס:</strong> {syllabusPreview.parsed.course_name || "לא זוהה"}</div>
              <div><strong>מוסד:</strong> {syllabusPreview.parsed.institution || "לא זוהה"}</div>
              <div><strong>סמסטר:</strong> {syllabusPreview.parsed.semester || "לא זוהה"}</div>
              <div><strong>שפה:</strong> {syllabusPreview.parsed.language || "לא זוהה"}</div>
              <div className="mt-2"><strong>מרצים שזוהו:</strong> {(syllabusPreview.parsed.lecturers || []).length}</div>
              <div><strong>הרצאות שזוהו:</strong> {(syllabusPreview.parsed.lectures || []).length}</div>

              <button
                onClick={createCourseFromSyllabus}
                disabled={creatingFromSyllabus}
                className="mt-4 rounded-xl bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-50"
              >
                {creatingFromSyllabus ? "יוצר..." : "צור קורס אוטומטית"}
              </button>
            </div>
          )}
        </section>
      )}

      {drawerOpen && (
        <div className="fixed inset-y-0 left-0 z-50 w-full max-w-xl border-r border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b p-4">
            <div className="font-semibold">
              {documentDetails ? `פרטי מסמך: ${documentDetails.file_name}` : "פרטי מסמך"}
            </div>
            <button
              onClick={() => setDrawerOpen(false)}
              className="rounded-lg bg-slate-100 px-3 py-1"
            >
              סגור
            </button>
          </div>

          <div className="h-[calc(100vh-73px)] overflow-y-auto p-4">
            {loadingDocumentDetails ? (
              <LoadingSkeleton lines={6} />
            ) : documentDetails ? (
              <div className="space-y-3 text-sm">
                <div><strong>סטטוס:</strong> {documentDetails.processing_status || "unknown"}</div>
                <div><strong>שפה:</strong> {documentDetails.language || "unknown"}</div>
                <div><strong>סוג מקור:</strong> {documentDetails.source_type || "unknown"}</div>
                <div><strong>נושא:</strong> {documentDetails.topic || "ללא נושא"}</div>
                <div><strong>הרצאה:</strong> {documentDetails.lecture_title || "ללא הרצאה"}</div>
                <div><strong>אורך טקסט שחולץ:</strong> {documentDetails.raw_text_length || 0} תווים</div>
                <div><strong>האם summary קיים:</strong> {documentDetails.has_summary ? "כן" : "לא"}</div>

                <div>
                  <div className="mb-1 font-semibold">שגיאה אחרונה</div>
                  <div className="max-h-32 overflow-y-auto rounded-xl bg-red-50 p-3 whitespace-pre-wrap text-red-700">
                    {documentDetails.last_error || "אין שגיאה שמורה"}
                  </div>
                </div>

                <div>
                  <div className="mb-1 font-semibold">Summary</div>
                  <div className="max-h-48 overflow-y-auto rounded-xl bg-slate-50 p-3 whitespace-pre-wrap">
                    {documentDetails.summary_text || "לא נוצר summary"}
                  </div>
                </div>

                <div>
                  <div className="mb-1 font-semibold">Raw text preview</div>
                  <div className="max-h-48 overflow-y-auto rounded-xl bg-slate-50 p-3 whitespace-pre-wrap">
                    {documentDetails.raw_text_preview || "לא חולץ טקסט"}
                  </div>
                </div>

                <div>
                  <button
                    onClick={() => retryDocumentProcessing(documentDetails.id)}
                    className="w-full rounded-xl bg-amber-500 px-4 py-2 font-medium text-white"
                  >
                    נסה שוב לעבד את המסמך
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}
