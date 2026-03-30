"use client"

import { useEffect, useState } from "react"

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

export default function KnowledgePage() {
  const [courses, setCourses] = useState<Course[]>([])
  const [lecturers, setLecturers] = useState<Lecturer[]>([])
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [documents, setDocuments] = useState<CourseDocument[]>([])
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [selectedLectureId, setSelectedLectureId] = useState("")
  const [error, setError] = useState("")

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
    const res = await fetch(`${API_BASE}/courses/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newCourse),
    })
    if (!res.ok) {
      setError("שגיאה ביצירת קורס")
      return
    }
    await fetchCourses()
    setNewCourse({
      name: "",
      institution: "",
      default_language: "en",
      semester: "",
      lecturer_name: "",
    })
  }

  async function createLecturer() {
    const res = await fetch(`${API_BASE}/lecturers/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newLecturer),
    })
    if (!res.ok) {
      setError("שגיאה ביצירת מרצה")
      return
    }
    await fetchLecturers()
    setNewLecturer({ full_name: "", bio: "" })
  }

  async function createLecture() {
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
    if (!res.ok) {
      setError("שגיאה ביצירת הרצאה")
      return
    }
    await fetchLectures(selectedCourseId)
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

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-red-700">
          {error}
        </div>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-4 text-2xl font-semibold">מרכז הידע</h2>
        <p className="text-sm text-slate-500">
          כאן מנהלים קורסים, מרצים, הרצאות וחומרי לימוד.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">קורסים</h3>
          <div className="mb-4 space-y-2">
            {courses.map((course) => (
              <button
                key={course.id}
                onClick={() => setSelectedCourseId(course.id)}
                className={`block w-full rounded-xl border px-3 py-3 text-right ${
                  selectedCourseId === course.id
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-200"
                }`}
              >
                <div className="font-medium">{course.name}</div>
                <div className="text-xs text-slate-500">
                  {course.institution || "ללא מוסד"} • {course.semester || "ללא סמסטר"}
                </div>
              </button>
            ))}
          </div>

          <div className="space-y-3">
            <input className="w-full rounded-lg border px-3 py-2" placeholder="שם קורס" value={newCourse.name} onChange={(e) => setNewCourse((p) => ({ ...p, name: e.target.value }))} />
            <input className="w-full rounded-lg border px-3 py-2" placeholder="מוסד" value={newCourse.institution} onChange={(e) => setNewCourse((p) => ({ ...p, institution: e.target.value }))} />
            <input className="w-full rounded-lg border px-3 py-2" placeholder="סמסטר" value={newCourse.semester} onChange={(e) => setNewCourse((p) => ({ ...p, semester: e.target.value }))} />
            <button onClick={createCourse} className="w-full rounded-lg bg-blue-600 px-4 py-2 font-medium text-white">צור קורס</button>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">מרצים</h3>
          <div className="mb-4 space-y-2">
            {lecturers.map((lecturer) => (
              <div key={lecturer.id} className="rounded-xl border border-slate-200 p-3">
                <div className="font-medium">{lecturer.full_name}</div>
                <div className="text-xs text-slate-500">{lecturer.bio || "ללא תיאור"}</div>
              </div>
            ))}
          </div>

          <div className="space-y-3">
            <input className="w-full rounded-lg border px-3 py-2" placeholder="שם המרצה" value={newLecturer.full_name} onChange={(e) => setNewLecturer((p) => ({ ...p, full_name: e.target.value }))} />
            <textarea className="w-full rounded-lg border px-3 py-2" placeholder="ביוגרפיה / הערות" value={newLecturer.bio} onChange={(e) => setNewLecturer((p) => ({ ...p, bio: e.target.value }))} />
            <button onClick={createLecturer} className="w-full rounded-lg bg-slate-800 px-4 py-2 font-medium text-white">צור מרצה</button>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">הרצאות</h3>

          <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-4">
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

          <button onClick={createLecture} className="mb-4 rounded-lg bg-purple-600 px-4 py-2 font-medium text-white">צור הרצאה</button>

          <div className="space-y-2">
            {lectures.map((lecture) => (
              <button
                key={lecture.id}
                onClick={() => setSelectedLectureId(lecture.id)}
                className={`block w-full rounded-xl border px-3 py-3 text-right ${
                  selectedLectureId === lecture.id
                    ? "border-purple-500 bg-purple-50"
                    : "border-slate-200"
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

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-4 text-lg font-semibold">מסמכים והעלאה</h3>

          <div className="mb-4 space-y-3">
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

          <div className="max-h-[360px] space-y-2 overflow-y-auto">
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
        </section>
      </div>
    </div>
  )
}
