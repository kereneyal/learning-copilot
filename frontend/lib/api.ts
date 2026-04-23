/**
 * Central API client for the Learning Copilot backend.
 *
 * All network calls go through `apiFetch` so that:
 *  - The base URL comes from one env var (NEXT_PUBLIC_API_BASE_URL).
 *  - Error handling is uniform: non-2xx responses throw ApiError.
 *  - Request/response types are co-located with the call site.
 *
 * Usage:
 *   import { api } from "@/lib/api"
 *   const courses = await api.courses.list()
 */

const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "")

// ── Error type ─────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message?: string,
  ) {
    super(message ?? `API error ${status}`)
    this.name = "ApiError"
  }
}

// ── Core fetch wrapper ─────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...init.headers },
    ...init,
  })

  if (!res.ok) {
    let body: unknown
    try {
      body = await res.json()
    } catch {
      body = await res.text().catch(() => null)
    }
    throw new ApiError(res.status, body)
  }

  // 204 No Content
  if (res.status === 204) return undefined as T

  return res.json() as Promise<T>
}

// Upload helper — does NOT set Content-Type so the browser sets multipart boundary.
async function apiFetchForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form })
  if (!res.ok) {
    let body: unknown
    try { body = await res.json() } catch { body = null }
    throw new ApiError(res.status, body)
  }
  return res.json() as Promise<T>
}

// ── Shared types ───────────────────────────────────────────────────────────────

export type Language = "he" | "en"

export type SummaryStatus =
  | "not_started"
  | "pending"
  | "generating"
  | "completed"
  | "failed"

export interface Pagination {
  total: number
  page: number
  page_size: number
  pages: number
}

export interface PaginatedResponse<T> {
  status: "success"
  message: string
  data: T[]
  pagination: Pagination
}

// ── Domain types ───────────────────────────────────────────────────────────────

export interface Course {
  id: string
  name: string
  institution: string | null
  default_language: Language | null
  semester: string | null
  lecturer_name: string | null
  created_at: string
}

export interface Lecture {
  id: string
  course_id: string
  lecturer_id: string | null
  title: string
  lecture_date: string | null
  notes: string | null
}

export interface CourseDocument {
  id: string
  course_id: string
  lecture_id: string | null
  file_name: string
  file_type: string | null
  processing_status: string
  processing_progress: number
  summary_status: SummaryStatus
  created_at: string
}

export interface DocumentDetails extends CourseDocument {
  raw_text: string | null
  error_type: string | null
  error_stage: string | null
  last_error: string | null
  language: Language | null
  topic: string | null
}

export interface Summary {
  id: string
  document_id: string
  summary_text: string
  language: Language
}

export interface CourseSummary {
  id: string
  course_id: string
  summary_text: string
  language: Language
}

export interface KnowledgeMap {
  id: string
  course_id: string
  map_text: string
  language: Language
}

export interface CopilotMessage {
  role: "user" | "assistant"
  content: string
}

export interface CopilotResponse {
  answer: string
  sources: SourceChunk[]
  question_type?: string
}

export interface SourceChunk {
  document_id: string
  file_name: string
  chunk_text: string
  score?: number
}

export interface HealthCheck {
  status: "ok" | "degraded"
  duration_ms: number
  checks: Record<string, { status: string; detail?: string }>
}

// ── API namespace ──────────────────────────────────────────────────────────────

export const api = {
  // ── Health ─────────────────────────────────────────────────────────────────
  health: {
    check: () => apiFetch<HealthCheck>("/health"),
  },

  // ── Courses ────────────────────────────────────────────────────────────────
  courses: {
    list: (page = 1, pageSize = 50) =>
      apiFetch<PaginatedResponse<Course>>(
        `/courses/?page=${page}&page_size=${pageSize}`,
      ),

    get: (courseId: string) =>
      apiFetch<{ status: string; data: Course }>(`/courses/${courseId}`),

    create: (payload: {
      name: string
      institution?: string
      default_language?: Language
      semester?: string
      lecturer_name?: string
    }) =>
      apiFetch<{ status: string; data: Course }>("/courses/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    update: (
      courseId: string,
      payload: Partial<{
        name: string
        institution: string
        default_language: Language
        semester: string
        lecturer_name: string
      }>,
    ) =>
      apiFetch<{ status: string; data: Course }>(`/courses/${courseId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),

    delete: (courseId: string) =>
      apiFetch<{ status: string; data: { deleted_course_id: string } }>(
        `/courses/${courseId}`,
        { method: "DELETE" },
      ),
  },

  // ── Lectures ───────────────────────────────────────────────────────────────
  lectures: {
    listByCourse: (courseId: string) =>
      apiFetch<Lecture[]>(`/lectures/?course_id=${courseId}`),

    create: (payload: {
      course_id: string
      title: string
      lecturer_id?: string
      lecture_date?: string
      notes?: string
    }) =>
      apiFetch<Lecture>("/lectures/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    delete: (lectureId: string) =>
      apiFetch<{ status: string }>(`/lectures/${lectureId}`, {
        method: "DELETE",
      }),
  },

  // ── Documents ──────────────────────────────────────────────────────────────
  documents: {
    listByCourse: (courseId: string) =>
      apiFetch<CourseDocument[]>(`/documents/course/${courseId}`),

    getDetails: (documentId: string) =>
      apiFetch<DocumentDetails>(`/documents/${documentId}/details`),

    getStatus: (documentId: string) =>
      apiFetch<{ id: string; processing_status: string; summary_status: SummaryStatus }>(
        `/documents/${documentId}/status`,
      ),

    upload: (form: FormData) => apiFetchForm<CourseDocument>("/documents/upload", form),

    delete: (documentId: string) =>
      apiFetch<{ status: string }>(`/documents/${documentId}`, {
        method: "DELETE",
      }),

    retrySummary: (documentId: string) =>
      apiFetch<{ status: string; summary_status: SummaryStatus }>(
        `/documents/${documentId}/retry-summary`,
        { method: "POST" },
      ),
  },

  // ── Summaries ──────────────────────────────────────────────────────────────
  summaries: {
    getByDocument: (documentId: string) =>
      apiFetch<Summary>(`/summaries/${documentId}`),
  },

  // ── Course summaries ───────────────────────────────────────────────────────
  courseSummaries: {
    getByCourse: (courseId: string) =>
      apiFetch<CourseSummary>(`/course-summaries/${courseId}`),
  },

  // ── Knowledge maps ─────────────────────────────────────────────────────────
  knowledgeMaps: {
    getByCourse: (courseId: string) =>
      apiFetch<KnowledgeMap>(`/knowledge-maps/${courseId}`),
  },

  // ── Copilot ────────────────────────────────────────────────────────────────
  copilot: {
    chat: (payload: {
      question: string
      course_id?: string
      lecture_id?: string
      history?: CopilotMessage[]
    }) =>
      apiFetch<CopilotResponse>("/copilot/chat", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },

  // ── Search ─────────────────────────────────────────────────────────────────
  search: {
    global: (query: string) =>
      apiFetch<{ results: unknown[] }>(`/search/?q=${encodeURIComponent(query)}`),
  },

  // ── Syllabus ───────────────────────────────────────────────────────────────
  syllabus: {
    preview: (form: FormData) =>
      apiFetchForm<{ parsed: unknown }>("/syllabus/preview", form),

    createFromParsed: (payload: unknown) =>
      apiFetch<{ course_id: string }>("/syllabus/create-from-parsed", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },

  // ── Exam ───────────────────────────────────────────────────────────────────
  exam: {
    generate: (payload: { course_id: string; num_questions?: number }) =>
      apiFetch<{ exam_id: string; questions: unknown[] }>("/exam/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    get: (examId: string) => apiFetch<unknown>(`/exam/${examId}`),
  },
}
