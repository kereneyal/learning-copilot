"use client"

import { useEffect, useState } from "react"
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

export default function KnowledgePage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [lecturers, setLecturers] = useState<Lecturer[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [documents, setDocuments] = useState<CourseDocument[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: "info" | "success" | "error" } | null>(null)

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
    file: null as File | null,
  })

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

  async function fetchCourses() {
    try {
      setLoading(true)
      const res = await fetch(`${API_BASE}/courses/`)
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
      const data = await res.json()
      setLecturers(data)
    } catch {
      setToast({ message: "שגיאה בטעינת מרצים", type: "error" })
    }
  }

  async function fetchLectures(courseId: string) {
    try {
      const res = await fetch(`${API_BASE}/lectures/course/${courseId}`)
      const data = await res.json()
      setLectures(data)
    } catch {
      setToast({ message: "שגיאה בטעינת הרצאות", type: "error" })
    }
  }

  async function fetchDocumentsByCourse(courseId: string) {
    try {
      const res = await fetch(`${API_BASE}/documents/course/${courseId}`)
      const data = await res.json()
      setDocuments(data)
    } catch {
      setToast({ message: "שגיאה בטעינת מסמכים", type: "error" })
    }
  }

  async function fetchDocumentsByLecture(lectureId: string) {
    try {
      const res = await fetch(`${API_BASE}/documents/lecture/${lectureId}`)
      const data = await res.json()
      setDocuments(data)
    } catch {
      setToast({ message: "שגיאה בטעינת מסמכי הרצאה", type: "error" })
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

  async function uploadFile() {
    try {
      if (!selectedCourseId || !selectedLectureId || !uploadForm.file) {
        setToast({ message: "יש לבחור קורס, הרצאה וקובץ", type: "error" })
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
      if (!res.ok) throw new Error()

      await fetchDocumentsByLecture(selectedLectureId)
      setToast({ message: "הקובץ הועלה בהצלחה", type: "success" })
      setUploadForm({
        topic: "",
        source_type: "slides",
        file: null,
      })
    } catch {
      setToast({ message: "שגיאה בהעלאת קובץ", type: "error" })
    }
  }

  async function saveCourseEdit() {
    if (!editingCourse) return

    try {
      const res = await fetch(`${API_BASE}/courses/${editingCourse.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editingCourse.name,
          institution: editingCourse.institution,
          semester: editingCourse.semester,
          default_language: editingCourse.default_language,
          lecturer_name: editingCourse.lecturer_name,
        }),
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
    const ok = window.confirm("למחוק את הקורס? פעולה זו תמחק גם הרצאות, מסמכים וידע קשור.")
    if (!ok) return

    try {
      const res = await fetch(`${API_BASE}/courses/${courseId}`, { method: "DELETE" })
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
    const ok = window.confirm("למחוק את ההרצאה? פעולה זו תמחק גם מסמכים קשורים.")
    if (!ok) return

    try {
      const res = await fetch(`${API_BASE}/lectures/${lectureId}`, { method: "DELETE" })
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
      await fetchLectures(selectedCourseId)
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
      } else {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setToast({ message: "המסמך עודכן בהצלחה", type: "success" })
      setEditingDocument(null)
    } catch {
      setToast({ message: "שגיאה בעדכון מסמך", type: "error" })
    }
  }

  async function deleteDocument(documentId: string) {
    const ok = window.confirm("למחוק את המסמך?")
    if (!ok) return

    try {
      const res = await fetch(`${API_BASE}/documents/${documentId}`, {
        method: "DELETE",
      })

      if (!res.ok) throw new Error()

      if (selectedLectureId) {
        await fetchDocumentsByLecture(selectedLectureId)
      } else {
        await fetchDocumentsByCourse(selectedCourseId)
      }

      setToast({ message: "המסמך נמחק בהצלחה", type: "success" })
    } catch {
      setToast({ message: "שגיאה במחיקת מסמך", type: "error" })
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold">מרכז הידע</h2>
        <p className="mt-1 text-sm text-slate-500">
          ניהול קורסים, הרצאות, מרצים וחומרי לימוד
        </p>
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
                <div key={course.id} className={`rounded-2xl border px-3 py-3 ${selectedCourseId === course.id ? "border-blue-500 bg-blue-50" : "border-slate-200"}`}>
                  <button onClick={() => setSelectedCourseId(course.id)} className="block w-full text-right">
                    <div className="font-medium">{course.name}</div>
                    <div className="text-xs text-slate-500">
                      {course.institution || "ללא מוסד"} • {course.semester || "ללא סמסטר"}
                    </div>
                  </button>

                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingCourse(course)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">ערוך</button>
                    <button onClick={() => deleteCourse(course.id)} className="rounded-lg bg-red-100 px-3 py-1 text-sm text-red-700">מחק</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            <input className="w-full rounded-xl border px-3 py-2" placeholder="שם קורס" value={newCourse.name} onChange={(e) => setNewCourse((p) => ({ ...p, name: e.target.value }))} />
            <input className="w-full rounded-xl border px-3 py-2" placeholder="מוסד" value={newCourse.institution} onChange={(e) => setNewCourse((p) => ({ ...p, institution: e.target.value }))} />
            <input className="w-full rounded-xl border px-3 py-2" placeholder="סמסטר" value={newCourse.semester} onChange={(e) => setNewCourse((p) => ({ ...p, semester: e.target.value }))} />
            <button onClick={createCourse} className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white">צור קורס</button>
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
                    <button onClick={() => setEditingLecturer(lecturer)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">ערוך</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            <input className="w-full rounded-xl border px-3 py-2" placeholder="שם המרצה" value={newLecturer.full_name} onChange={(e) => setNewLecturer((p) => ({ ...p, full_name: e.target.value }))} />
            <textarea className="w-full rounded-xl border px-3 py-2" placeholder="ביוגרפיה / הערות" value={newLecturer.bio} onChange={(e) => setNewLecturer((p) => ({ ...p, bio: e.target.value }))} />
            <button onClick={createLecturer} className="w-full rounded-xl bg-slate-800 px-4 py-2 font-medium text-white">צור מרצה</button>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">הרצאות</h3>

          <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-4">
            <input className="rounded-xl border px-3 py-2" placeholder="כותרת הרצאה" value={newLecture.title} onChange={(e) => setNewLecture((p) => ({ ...p, title: e.target.value }))} />
            <select className="rounded-xl border px-3 py-2" value={newLecture.lecturer_id} onChange={(e) => setNewLecture((p) => ({ ...p, lecturer_id: e.target.value }))}>
              <option value="">בחר מרצה</option>
              {lecturers.map((lecturer) => (
                <option key={lecturer.id} value={lecturer.id}>{lecturer.full_name}</option>
              ))}
            </select>
            <input className="rounded-xl border px-3 py-2" placeholder="תאריך הרצאה" value={newLecture.lecture_date} onChange={(e) => setNewLecture((p) => ({ ...p, lecture_date: e.target.value }))} />
            <input className="rounded-xl border px-3 py-2" placeholder="הערות" value={newLecture.notes} onChange={(e) => setNewLecture((p) => ({ ...p, notes: e.target.value }))} />
          </div>

          <button onClick={createLecture} className="mb-4 rounded-xl bg-purple-600 px-4 py-2 font-medium text-white">צור הרצאה</button>

          {lectures.length === 0 ? (
            <EmptyState title="עדיין אין הרצאות" description="בחר קורס וצור הרצאות כדי להמשיך." />
          ) : (
            <div className="space-y-2">
              {lectures.map((lecture) => (
                <div key={lecture.id} className={`rounded-2xl border px-3 py-3 ${selectedLectureId === lecture.id ? "border-purple-500 bg-purple-50" : "border-slate-200"}`}>
                  <button onClick={() => setSelectedLectureId(lecture.id)} className="block w-full text-right">
                    <div className="font-medium">{lecture.title}</div>
                    <div className="text-xs text-slate-500">
                      {lecture.lecturer_name || "ללא מרצה"} • {lecture.lecture_date || "ללא תאריך"}
                    </div>
                  </button>

                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingLecture(lecture)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">ערוך</button>
                    <button onClick={() => deleteLecture(lecture.id)} className="rounded-lg bg-red-100 px-3 py-1 text-sm text-red-700">מחק</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">מסמכים והעלאה</h3>

          <div className="mb-4 space-y-3">
            <input className="w-full rounded-xl border px-3 py-2" placeholder="נושא" value={uploadForm.topic} onChange={(e) => setUploadForm((p) => ({ ...p, topic: e.target.value }))} />
            <select className="w-full rounded-xl border px-3 py-2" value={uploadForm.source_type} onChange={(e) => setUploadForm((p) => ({ ...p, source_type: e.target.value }))}>
              <option value="slides">מצגת</option>
              <option value="summary">סיכום</option>
              <option value="notes">הערות</option>
              <option value="article">מאמר</option>
            </select>
            <input className="w-full rounded-xl border px-3 py-2" type="file" onChange={(e) => setUploadForm((p) => ({ ...p, file: e.target.files?.[0] || null }))} />
            <button onClick={uploadFile} className="w-full rounded-xl bg-emerald-600 px-4 py-2 font-medium text-white">העלה חומר להרצאה</button>
          </div>

          {documents.length === 0 ? (
            <EmptyState title="אין מסמכים" description="בחר הרצאה והעלה חומר לימוד." />
          ) : (
            <div className="max-h-[360px] space-y-2 overflow-y-auto">
              {documents.map((doc) => (
                <div key={doc.id} className="rounded-2xl border border-slate-200 px-3 py-3">
                  <div className="font-medium">{doc.file_name}</div>
                  <div className="text-xs text-slate-500">
                    {doc.lecture_title ? `${doc.lecture_title} • ` : ""}
                    {doc.file_type || "unknown"} • {doc.language || "unknown"} • {doc.topic || "ללא נושא"}
                  </div>

                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setEditingDocument(doc)} className="rounded-lg bg-slate-100 px-3 py-1 text-sm">ערוך</button>
                    <button onClick={() => deleteDocument(doc.id)} className="rounded-lg bg-red-100 px-3 py-1 text-sm text-red-700">מחק</button>
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
            <input className="w-full rounded-xl border px-3 py-2" value={editingCourse.name} onChange={(e) => setEditingCourse({ ...editingCourse, name: e.target.value })} />
            <input className="w-full rounded-xl border px-3 py-2" value={editingCourse.institution || ""} onChange={(e) => setEditingCourse({ ...editingCourse, institution: e.target.value })} />
            <input className="w-full rounded-xl border px-3 py-2" value={editingCourse.semester || ""} onChange={(e) => setEditingCourse({ ...editingCourse, semester: e.target.value })} />
            <button onClick={saveCourseEdit} className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white">שמור שינויים</button>
          </div>
        </Modal>
      )}

      {editingLecture && (
        <Modal title="עריכת הרצאה" onClose={() => setEditingLecture(null)}>
          <div className="space-y-3">
            <input className="w-full rounded-xl border px-3 py-2" value={editingLecture.title} onChange={(e) => setEditingLecture({ ...editingLecture, title: e.target.value })} />
            <select className="w-full rounded-xl border px-3 py-2" value={editingLecture.lecturer_id} onChange={(e) => setEditingLecture({ ...editingLecture, lecturer_id: e.target.value })}>
              <option value="">בחר מרצה</option>
              {lecturers.map((lecturer) => (
                <option key={lecturer.id} value={lecturer.id}>{lecturer.full_name}</option>
              ))}
            </select>
            <input className="w-full rounded-xl border px-3 py-2" value={editingLecture.lecture_date || ""} onChange={(e) => setEditingLecture({ ...editingLecture, lecture_date: e.target.value })} />
            <input className="w-full rounded-xl border px-3 py-2" value={editingLecture.notes || ""} onChange={(e) => setEditingLecture({ ...editingLecture, notes: e.target.value })} />
            <button onClick={saveLectureEdit} className="w-full rounded-xl bg-purple-600 px-4 py-2 font-medium text-white">שמור שינויים</button>
          </div>
        </Modal>
      )}

      {editingLecturer && (
        <Modal title="עריכת מרצה" onClose={() => setEditingLecturer(null)}>
          <div className="space-y-3">
            <input className="w-full rounded-xl border px-3 py-2" value={editingLecturer.full_name} onChange={(e) => setEditingLecturer({ ...editingLecturer, full_name: e.target.value })} />
            <textarea className="w-full rounded-xl border px-3 py-2" value={editingLecturer.bio || ""} onChange={(e) => setEditingLecturer({ ...editingLecturer, bio: e.target.value })} />
            <button onClick={saveLecturerEdit} className="w-full rounded-xl bg-slate-800 px-4 py-2 font-medium text-white">שמור שינויים</button>
          </div>
        </Modal>
      )}

      {editingDocument && (
        <Modal title="עריכת מסמך" onClose={() => setEditingDocument(null)}>
          <div className="space-y-3">
            <input className="w-full rounded-xl border px-3 py-2" value={editingDocument.file_name} onChange={(e) => setEditingDocument({ ...editingDocument, file_name: e.target.value })} />
            <input className="w-full rounded-xl border px-3 py-2" value={editingDocument.topic || ""} onChange={(e) => setEditingDocument({ ...editingDocument, topic: e.target.value })} />
            <select className="w-full rounded-xl border px-3 py-2" value={editingDocument.source_type || ""} onChange={(e) => setEditingDocument({ ...editingDocument, source_type: e.target.value })}>
              <option value="slides">מצגת</option>
              <option value="summary">סיכום</option>
              <option value="notes">הערות</option>
              <option value="article">מאמר</option>
            </select>
            <button onClick={saveDocumentEdit} className="w-full rounded-xl bg-emerald-600 px-4 py-2 font-medium text-white">שמור שינויים</button>
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
