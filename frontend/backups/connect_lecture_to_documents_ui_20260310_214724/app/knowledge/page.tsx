"use client"

import { useEffect, useMemo, useState } from "react"
import Toast from "../components/Toast"
import LoadingSkeleton from "../components/LoadingSkeleton"
import EmptyState from "../components/EmptyState"
import Modal from "../components/Modal"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"

type Course = {
  id: string
  name: string
  institution?: string
  semester?: string
  default_language?: string
  lecturer_name?: string
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
}

type ToastState = {
  message: string
  type: "info" | "success" | "error"
} | null

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

export default function KnowledgePage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [lecturers, setLecturers] = useState<Lecturer[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [documents, setDocuments] = useState<CourseDocument[]>([])

  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")

  const [loading, setLoading] = useState(false)
  const [uploadingBatch, setUploadingBatch] = useState(false)
  const [toast, setToast] = useState<ToastState>(null)

  const [editingCourse, setEditingCourse] = useState<Course | null>(null)
  const [editingLecture, setEditingLecture] = useState<Lecture | null>(null)
  const [editingLecturer, setEditingLecturer] = useState<Lecturer | null>(null)
  const [editingDocument, setEditingDocument] = useState<CourseDocument | null>(null)

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
      setSelectedLectureId("")
    }
  }, [selectedCourseId])

  useEffect(() => {
    if (selectedLectureId) {
      fetchDocumentsByLecture(selectedLectureId)
    }
  }, [selectedLectureId])

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
    } catch {
      if (showErrorToast) {
        setToast({ message: "שגיאה בטעינת מסמכים", type: "error" })
      }
    }
  }

  async function fetchDocumentsByLecture(lectureId: string, showErrorToast = true) {
    try {
      const res = await fetch(`${API_BASE}/documents/lecture/${lectureId}`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setDocuments(data)
    } catch {
      if (showErrorToast) {
        setToast({ message: "שגיאה בטעינת מסמכי הרצאה", type: "error" })
      }
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

      if (data?.course?.id) {
        setSelectedCourseId(data.course.id)
      }

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
        lecturer_name: "",
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
      if (!selectedCourseId || !selectedLectureId || uploadForm.files.length === 0) {
        setToast({ message: "יש לבחור קורס, הרצאה ולפחות קובץ אחד", type: "error" })
        return
      }

      setUploadingBatch(true)

      const formData = new FormData()
      formData.append("course_id", selectedCourseId)
      formData.append("lecture_id", selectedLectureId)
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

      await fetchDocumentsByLecture(selectedLectureId)

      setToast({
        message: "העלאת הקבצים הושלמה. הסטטוסים יתעדכנו אוטומטית.",
        type: "success",
      })

      setUploadForm({
        topic: "",
        source_type: "slides",
        files: [],
      })
    } catch {
      setToast({ message: "שגיאה בהעלאת קבצים", type: "error" })
    } finally {
      setUploadingBatch(false)
    }
  }

  async function saveCourseEdit() {
    if (!editingCourse) return

    try {
      const res = await fetch(`${API_BASE}/courses/${editingCourse.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editingCourse),
      })
      if (!res.ok) throw new Error()

      await fetchCourses()
      setToast({ message: "הקורס עודכן בהצלחה", type: "success" })
      setEditingCourse(null)
    } catch {
      setToast({ message: "שגיאה בעדכון קורס", type: "error" })
    }
  }

  async function deleteCourse(courseId: string) {
    if (!window.confirm("למחוק את הקורס? פעולה זו תמחק גם הרצאות, מסמכים וידע קשור.")) {
      return
    }

    try {
      const res = await fetch(`${API_BASE}/courses/${courseId}`, {
        method: "DELETE",
      })
      if (!res.ok) throw new Error()

      await fetchCourses()

      if (selectedCourseId === courseId) {
        setSelectedCourseId("")
        setSelectedLectureId("")
        setLectures([])
        setDocuments([])
      }

      setToast({ message: "הקורס נמחק בהצלחה", type: "success" })
    } catch {
      setToast({ message: "שגיאה במחיקת קורס", type: "error" })
    }
  }

  async function saveLectureEdit() {
    if (!editingLecture) return

    try {
      const res = await fetch(`${API_BASE}/lectures/${editingLecture.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lecturer_id: editingLecture.lecturer_id,
          title: editingLecture.title,
          lecture_date: editingLecture.lecture_date,
          notes: editingLecture.notes,
        }),
      })
      if (!res.ok) throw new Error()

      await fetchLectures(editingLecture.course_id)
      setToast({ message: "ההרצאה עודכנה בהצלחה", type: "success" })
      setEditingLecture(null)
    } catch {
      setToast({ message: "שגיאה בעדכון הרצאה", type: "error" })
    }
  }

  async function deleteLecture(lectureId: string) {
    if (!window.confirm("למחוק את ההרצאה? פעולה זו תמחק גם מסמכים קשורים.")) {
      return
    }

    try {
      const res = await fetch(`${API_BASE}/lectures/${lectureId}`, {
        method: "DELETE",
      })
      if (!res.ok) throw new Error()

      await fetchLectures(selectedCourseId)
      if (selectedLectureId === lectureId) {
        setSelectedLectureId("")
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setToast({ message: "ההרצאה נמחקה בהצלחה", type: "success" })
    } catch {
      setToast({ message: "שגיאה במחיקת הרצאה", type: "error" })
    }
  }

  async function saveLecturerEdit() {
    if (!editingLecturer) return

    try {
      const res = await fetch(`${API_BASE}/lecturers/${editingLecturer.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: editingLecturer.full_name,
          bio: editingLecturer.bio,
        }),
      })
      if (!res.ok) throw new Error()

      await fetchLecturers()
      if (selectedCourseId) {
        await fetchLectures(selectedCourseId)
      }

      setToast({ message: "המרצה עודכן בהצלחה", type: "success" })
      setEditingLecturer(null)
    } catch {
      setToast({ message: "שגיאה בעדכון מרצה", type: "error" })
    }
  }

  async function saveDocumentEdit() {
    if (!editingDocument) return

    try {
      const res = await fetch(`${API_BASE}/documents/${editingDocument.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_name: editingDocument.file_name,
          topic: editingDocument.topic,
          source_type: editingDocument.source_type,
        }),
      })
      if (!res.ok) throw new Error()

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else if (selectedCourseId) {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setToast({ message: "המסמך עודכן בהצלחה", type: "success" })
      setEditingDocument(null)
    } catch {
      setToast({ message: "שגיאה בעדכון מסמך", type: "error" })
    }
  }

  async function deleteDocument(documentId: string) {
    if (!window.confirm("למחוק את המסמך?")) return

    try {
      const res = await fetch(`${API_BASE}/documents/${documentId}`, {
        method: "DELETE",
      })
      if (!res.ok) throw new Error()

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else if (selectedCourseId) {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setToast({ message: "המסמך נמחק בהצלחה", type: "success" })
    } catch {
      setToast({ message: "שגיאה במחיקת מסמך", type: "error" })
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

    return (
      <span className={`rounded-full px-2 py-1 text-xs ${styles}`}>
        {label}
      </span>
    )
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold">מרכז הידע</h2>
        <p className="mt-1 text-sm text-slate-500">
          ניהול קורסים, הרצאות, מרצים וחומרי לימוד
        </p>
      </section>

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

            {syllabusPreview.parsed.lecturers && syllabusPreview.parsed.lecturers.length > 0 && (
              <div className="mt-3">
                <div className="mb-1 font-medium">מרצים:</div>
                <ul className="list-disc pr-5">
                  {syllabusPreview.parsed.lecturers.map((l, idx) => (
                    <li key={idx}>{l.full_name}</li>
                  ))}
                </ul>
              </div>
            )}

            {syllabusPreview.parsed.lectures && syllabusPreview.parsed.lectures.length > 0 && (
              <div className="mt-3">
                <div className="mb-1 font-medium">הרצאות:</div>
                <ul className="list-disc pr-5">
                  {syllabusPreview.parsed.lectures.slice(0, 10).map((l, idx) => (
                    <li key={idx}>
                      {l.title}
                      {l.lecturer_name ? ` • ${l.lecturer_name}` : ""}
                    </li>
                  ))}
                </ul>
                {syllabusPreview.parsed.lectures.length > 10 && (
                  <div className="mt-1 text-xs text-slate-500">
                    ועוד {syllabusPreview.parsed.lectures.length - 10} הרצאות...
                  </div>
                )}
              </div>
            )}

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

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">קורסים</h3>

          {loading ? (
            <LoadingSkeleton lines={4} />
          ) : courses.length === 0 ? (
            <EmptyState title="עדיין אין קורסים" description="צור את הקורס הראשון כדי להתחיל." />
          ) : (
            <div className="mb-4 space-y-2">
              {courses.map((course) => (
                <div
                  key={course.id}
                  className={`rounded-2xl border px-3 py-3 ${
                    selectedCourseId === course.id ? "border-blue-500 bg-blue-50" : "border-slate-200"
                  }`}
                >
                  <button onClick={() => setSelectedCourseId(course.id)} className="block w-full text-right">
                    <div className="font-medium">{course.name}</div>
                    <div className="text-xs text-slate-500">
                      {course.institution || "ללא מוסד"} • {course.semester || "ללא סמסטר"}
                    </div>
                  </button>

                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingCourse(course)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">
                      ערוך
                    </button>
                    <button onClick={() => deleteCourse(course.id)} className="rounded-lg bg-red-100 px-3 py-1 text-sm text-red-700">
                      מחק
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              placeholder="שם קורס"
              value={newCourse.name}
              onChange={(e) => setNewCourse((p) => ({ ...p, name: e.target.value }))}
            />
            <input
              className="w-full rounded-xl border px-3 py-2"
              placeholder="מוסד"
              value={newCourse.institution}
              onChange={(e) => setNewCourse((p) => ({ ...p, institution: e.target.value }))}
            />
            <input
              className="w-full rounded-xl border px-3 py-2"
              placeholder="סמסטר"
              value={newCourse.semester}
              onChange={(e) => setNewCourse((p) => ({ ...p, semester: e.target.value }))}
            />
            <button onClick={createCourse} className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white">
              צור קורס
            </button>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">מרצים</h3>

          {lecturers.length === 0 ? (
            <EmptyState title="עדיין אין מרצים" description="הוסף מרצים כדי לשייך אותם להרצאות." />
          ) : (
            <div className="mb-4 space-y-2">
              {lecturers.map((lecturer) => (
                <div key={lecturer.id} className="rounded-2xl border border-slate-200 p-3">
                  <div className="font-medium">{lecturer.full_name}</div>
                  <div className="text-xs text-slate-500">{lecturer.bio || "ללא תיאור"}</div>
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingLecturer(lecturer)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">
                      ערוך
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              placeholder="שם המרצה"
              value={newLecturer.full_name}
              onChange={(e) => setNewLecturer((p) => ({ ...p, full_name: e.target.value }))}
            />
            <textarea
              className="w-full rounded-xl border px-3 py-2"
              placeholder="ביוגרפיה / הערות"
              value={newLecturer.bio}
              onChange={(e) => setNewLecturer((p) => ({ ...p, bio: e.target.value }))}
            />
            <button onClick={createLecturer} className="w-full rounded-xl bg-slate-800 px-4 py-2 font-medium text-white">
              צור מרצה
            </button>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">הרצאות</h3>
            {selectedCourse && (
              <span className="text-sm text-slate-500">
                קורס נבחר: {selectedCourse.name}
              </span>
            )}
          </div>

          <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-4">
            <input
              className="rounded-xl border px-3 py-2"
              placeholder="כותרת הרצאה"
              value={newLecture.title}
              onChange={(e) => setNewLecture((p) => ({ ...p, title: e.target.value }))}
            />
            <select
              className="rounded-xl border px-3 py-2"
              value={newLecture.lecturer_id}
              onChange={(e) => setNewLecture((p) => ({ ...p, lecturer_id: e.target.value }))}
            >
              <option value="">בחר מרצה</option>
              {lecturers.map((lecturer) => (
                <option key={lecturer.id} value={lecturer.id}>
                  {lecturer.full_name}
                </option>
              ))}
            </select>
            <input
              className="rounded-xl border px-3 py-2"
              placeholder="תאריך הרצאה"
              value={newLecture.lecture_date}
              onChange={(e) => setNewLecture((p) => ({ ...p, lecture_date: e.target.value }))}
            />
            <input
              className="rounded-xl border px-3 py-2"
              placeholder="הערות"
              value={newLecture.notes}
              onChange={(e) => setNewLecture((p) => ({ ...p, notes: e.target.value }))}
            />
          </div>

          <button onClick={createLecture} className="mb-4 rounded-xl bg-purple-600 px-4 py-2 font-medium text-white">
            צור הרצאה
          </button>

          {lectures.length === 0 ? (
            <EmptyState title="עדיין אין הרצאות" description="בחר קורס וצור הרצאות כדי להמשיך." />
          ) : (
            <div className="space-y-2">
              {lectures.map((lecture) => (
                <div
                  key={lecture.id}
                  className={`rounded-2xl border px-3 py-3 ${
                    selectedLectureId === lecture.id ? "border-purple-500 bg-purple-50" : "border-slate-200"
                  }`}
                >
                  <button onClick={() => setSelectedLectureId(lecture.id)} className="block w-full text-right">
                    <div className="font-medium">{lecture.title}</div>
                    <div className="text-xs text-slate-500">
                      {lecture.lecturer_name || "ללא מרצה"} • {lecture.lecture_date || "ללא תאריך"}
                    </div>
                  </button>

                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingLecture(lecture)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">
                      ערוך
                    </button>
                    <button onClick={() => deleteLecture(lecture.id)} className="rounded-lg bg-red-100 px-3 py-1 text-sm text-red-700">
                      מחק
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold">מסמכים והעלאה</h3>
            {selectedLecture && (
              <span className="text-sm text-slate-500">
                הרצאה נבחרת: {selectedLecture.title}
              </span>
            )}
          </div>

          <div className="mb-4 space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              placeholder="נושא"
              value={uploadForm.topic}
              onChange={(e) => setUploadForm((p) => ({ ...p, topic: e.target.value }))}
            />
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={uploadForm.source_type}
              onChange={(e) => setUploadForm((p) => ({ ...p, source_type: e.target.value }))}
            >
              <option value="slides">מצגת</option>
              <option value="summary">סיכום</option>
              <option value="notes">הערות</option>
              <option value="article">מאמר</option>
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

          {documents.length === 0 ? (
            <EmptyState title="אין מסמכים" description="בחר הרצאה והעלה חומר לימוד." />
          ) : (
            <div className="max-h-[360px] space-y-2 overflow-y-auto">
              {documents.map((doc) => (
                <div key={doc.id} className="rounded-2xl border border-slate-200 px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{doc.file_name}</div>
                      <div className="text-xs text-slate-500">
                        {doc.lecture_title ? `${doc.lecture_title} • ` : ""}
                        {doc.file_type || "unknown"} • {doc.language || "unknown"} • {doc.topic || "ללא נושא"}
                      </div>
                    </div>
                    {renderStatusBadge(doc.processing_status)}
                  </div>

                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingDocument(doc)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">
                      ערוך
                    </button>
                    <button onClick={() => deleteDocument(doc.id)} className="rounded-lg bg-red-100 px-3 py-1 text-sm text-red-700">
                      מחק
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {editingCourse && (
        <Modal title="עריכת קורס" onClose={() => setEditingCourse(null)}>
          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingCourse.name}
              onChange={(e) => setEditingCourse({ ...editingCourse, name: e.target.value })}
            />
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingCourse.institution || ""}
              onChange={(e) => setEditingCourse({ ...editingCourse, institution: e.target.value })}
            />
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingCourse.semester || ""}
              onChange={(e) => setEditingCourse({ ...editingCourse, semester: e.target.value })}
            />
            <button onClick={saveCourseEdit} className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white">
              שמור שינויים
            </button>
          </div>
        </Modal>
      )}

      {editingLecture && (
        <Modal title="עריכת הרצאה" onClose={() => setEditingLecture(null)}>
          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingLecture.title}
              onChange={(e) => setEditingLecture({ ...editingLecture, title: e.target.value })}
            />
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={editingLecture.lecturer_id || ""}
              onChange={(e) => setEditingLecture({ ...editingLecture, lecturer_id: e.target.value || null })}
            >
              <option value="">בחר מרצה</option>
              {lecturers.map((lecturer) => (
                <option key={lecturer.id} value={lecturer.id}>
                  {lecturer.full_name}
                </option>
              ))}
            </select>
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingLecture.lecture_date || ""}
              onChange={(e) => setEditingLecture({ ...editingLecture, lecture_date: e.target.value })}
            />
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingLecture.notes || ""}
              onChange={(e) => setEditingLecture({ ...editingLecture, notes: e.target.value })}
            />
            <button onClick={saveLectureEdit} className="w-full rounded-xl bg-purple-600 px-4 py-2 font-medium text-white">
              שמור שינויים
            </button>
          </div>
        </Modal>
      )}

      {editingLecturer && (
        <Modal title="עריכת מרצה" onClose={() => setEditingLecturer(null)}>
          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingLecturer.full_name}
              onChange={(e) => setEditingLecturer({ ...editingLecturer, full_name: e.target.value })}
            />
            <textarea
              className="w-full rounded-xl border px-3 py-2"
              value={editingLecturer.bio || ""}
              onChange={(e) => setEditingLecturer({ ...editingLecturer, bio: e.target.value })}
            />
            <button onClick={saveLecturerEdit} className="w-full rounded-xl bg-slate-800 px-4 py-2 font-medium text-white">
              שמור שינויים
            </button>
          </div>
        </Modal>
      )}

      {editingDocument && (
        <Modal title="עריכת מסמך" onClose={() => setEditingDocument(null)}>
          <div className="space-y-3">
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingDocument.file_name}
              onChange={(e) => setEditingDocument({ ...editingDocument, file_name: e.target.value })}
            />
            <input
              className="w-full rounded-xl border px-3 py-2"
              value={editingDocument.topic || ""}
              onChange={(e) => setEditingDocument({ ...editingDocument, topic: e.target.value })}
            />
            <select
              className="w-full rounded-xl border px-3 py-2"
              value={editingDocument.source_type || "slides"}
              onChange={(e) => setEditingDocument({ ...editingDocument, source_type: e.target.value })}
            >
              <option value="slides">מצגת</option>
              <option value="summary">סיכום</option>
              <option value="notes">הערות</option>
              <option value="article">מאמר</option>
            </select>
            <button onClick={saveDocumentEdit} className="w-full rounded-xl bg-emerald-600 px-4 py-2 font-medium text-white">
              שמור שינויים
            </button>
          </div>
        </Modal>
      )}

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  )
}

