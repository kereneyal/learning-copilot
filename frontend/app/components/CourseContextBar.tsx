type Course = {
  id: string
  name: string
  institution?: string
  semester?: string
}

type Lecture = {
  id: string
  title: string
  lecturer_name?: string
  lecture_date?: string
}

export default function CourseContextBar({
  selectedCourse,
  selectedLecture,
  chatMode,
  setChatMode,
}: {
  selectedCourse?: Course
  selectedLecture?: Lecture
  chatMode: "auto" | "global" | "course" | "lecture"
  setChatMode: (mode: "auto" | "global" | "course" | "lecture") => void
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h2 className="text-2xl font-semibold">
            {selectedCourse?.name || "ללא קורס נבחר"}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {selectedCourse?.institution || "ללא מוסד"} • {selectedCourse?.semester || "ללא סמסטר"}
          </p>
          {selectedLecture && (
            <p className="mt-2 text-sm text-slate-600">
              הרצאה נבחרת: <span className="font-medium">{selectedLecture.title}</span>
              {selectedLecture.lecturer_name ? ` • ${selectedLecture.lecturer_name}` : ""}
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <button onClick={() => setChatMode("auto")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "auto" ? "bg-blue-600 text-white" : "bg-slate-100"}`}>אוטומטי</button>
          <button onClick={() => setChatMode("global")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "global" ? "bg-blue-600 text-white" : "bg-slate-100"}`}>כל הקורסים</button>
          <button onClick={() => setChatMode("course")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "course" ? "bg-blue-600 text-white" : "bg-slate-100"}`}>הקורס הנוכחי</button>
          <button onClick={() => setChatMode("lecture")} className={`rounded-lg px-3 py-2 text-sm ${chatMode === "lecture" ? "bg-blue-600 text-white" : "bg-slate-100"}`}>ההרצאה הנוכחית</button>
        </div>
      </div>
    </section>
  )
}
