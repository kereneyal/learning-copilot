# AI Learning Copilot

An AI-powered academic assistant that ingests course materials (PDFs, slides, recordings) and turns them into a searchable knowledge base, auto-generated summaries, Q&A copilot, and practice exams.

---

## Features

- **AI Copilot** — Ask questions in Hebrew or English; answers cite the exact source chunk
- **Document Processing** — Upload PDF, DOCX, PPTX, or images; OCR-first pipeline with vision fallback for scanned documents
- **Knowledge Center** — Per-document summaries generated in the background; course-level aggregate summaries and knowledge maps
- **Exam Simulation** — Auto-generate practice exams from uploaded materials
- **Hybrid RAG** — Vector search (ChromaDB + nomic-embed-text) combined with BM25 lexical search for high-recall retrieval
- **Dual LLM Support** — Routes to local Ollama or OpenAI; configurable per task type (Q&A, summaries, definitions)
- **Hebrew-first** — RTL UI, Hebrew intent detection, domain-gating for legal/governance terms

---

## Architecture

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│   Next.js Frontend      │  HTTP  │   FastAPI Backend             │
│   (React 19 / TS / TW)  │◄──────►│   (Python 3.11 / SQLAlchemy) │
└─────────────────────────┘        └──────────┬───────────────────┘
                                              │
                          ┌───────────────────┼──────────────────┐
                          │                   │                  │
                   ┌──────▼──────┐   ┌────────▼──────┐  ┌───────▼──────┐
                   │   SQLite    │   │   ChromaDB    │  │ Ollama/OpenAI│
                   │  (ORM data) │   │ (vector store)│  │  (LLM calls) │
                   └─────────────┘   └───────────────┘  └──────────────┘
```

### Backend layers

| Layer | Path | Responsibility |
|---|---|---|
| Routes | `app/routes/` | HTTP endpoints, request validation (Pydantic) |
| Services | `app/services/` | Business logic, ChromaDB, hybrid retrieval |
| Agents | `app/agents/` | LLM orchestration (summary, Q&A, knowledge map) |
| Models | `app/models/` | SQLAlchemy ORM |
| Core | `app/core/` | Structured logging, response helpers |
| Middleware | `app/middleware/` | Per-request tracing, structured HTTP logs |

### Document processing pipeline

```
Upload → Ingestion (OCR / vision) → Chunking → Embedding (Ollama)
      → Vector Index (ChromaDB) + SQLite
      → [background] Summarization → Course aggregate refresh
```

---

## Quick Start (local, no Docker)

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | |
| Node.js | ≥ 20 | |
| Ollama | latest | [ollama.ai](https://ollama.ai) |
| Tesseract | ≥ 5 | `brew install tesseract tesseract-lang` |

### 1. Clone

```bash
git clone https://github.com/kereneyal/learning-copilot.git
cd learning-copilot
```

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set OPENAI_API_KEY if you want OpenAI provider

uvicorn app.main:app --reload
# → http://127.0.0.1:8000  (API docs at /docs)
```

### 3. Pull Ollama models

```bash
ollama pull nomic-embed-text      # embeddings (required)
ollama pull qwen2:0.5b            # generation (fast, CPU-friendly)
```

### 4. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local  # already points to http://127.0.0.1:8000
npm run dev
# → http://localhost:3000
```

---

## Docker (recommended for staging / production)

```bash
# Build and start all services (backend, frontend, ollama)
docker compose up --build

# Pull models into the Ollama container (first run only)
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull qwen2:0.5b
```

Services:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Ollama | http://localhost:11434 |

Persistent data is stored in named Docker volumes (`backend_db`, `backend_chroma`, `backend_storage`, `ollama_data`).

---

## Environment Variables

### Backend (`backend/.env`)

#### Server

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | `json` | `json` (structured) or `text` (human-readable) |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `CHROMA_DB_PATH` | `./chroma_db` | ChromaDB storage directory |

#### LLM providers

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(unset)* | Required when any provider is set to `openai` |
| `OPENAI_MODEL` | `gpt-4.1-mini` | OpenAI model for Q&A |
| `OPENAI_TIMEOUT` | `30` | Request timeout (seconds) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_GENERATION_MODEL` | `qwen2:0.5b` | Generation model name |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model name |
| `OLLAMA_GENERATION_TIMEOUT` | `45` | Ollama generation timeout (seconds) |

#### Provider routing

| Variable | Default | Description |
|---|---|---|
| `QA_PROVIDER_DEFAULT` | `ollama` | Default Q&A provider (`ollama` / `openai`) |
| `QA_PROVIDER_DEFINITION` | `openai` | Provider for definition/acronym questions |
| `SUMMARY_PROVIDER` | auto | `openai` / `ollama` / auto-detect |
| `SUMMARY_TIMEOUT_S` | `30` | Summary generation timeout |
| `AGGREGATES_PROVIDER` | auto | Provider for course summaries + knowledge maps |
| `AGGREGATES_TIMEOUT_S` | `30` | Aggregate generation timeout |

#### Retrieval tuning

| Variable | Default | Description |
|---|---|---|
| `QA_MAX_CONTEXT_CHUNKS` | `3` | Max chunks forwarded to LLM |
| `QA_MAX_CHUNK_CHARS` | `400` | Max characters per chunk |
| `EMBED_WORKERS` | `1` | Parallel embedding workers (1 = serial, for CPU Ollama) |
| `EMBED_SINGLE_TIMEOUT_S` | `90` | Per-request embedding timeout |
| `DOMAIN_GATE_ENABLED` | `false` | Require Hebrew governance terms in retrieved chunks |

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Backend base URL |

---

## API Reference

Interactive docs available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the backend is running.

### Key endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health — DB, ChromaDB, Ollama |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/courses/` | List courses (paginated: `?page=1&page_size=50`) |
| `POST` | `/courses/` | Create course |
| `DELETE` | `/courses/{id}` | Delete course + all data |
| `POST` | `/documents/upload` | Upload document (multipart form) |
| `GET` | `/documents/{id}/status` | Processing + summary status |
| `GET` | `/documents/{id}/details` | Full document details |
| `POST` | `/documents/{id}/retry-summary` | Retry failed summary |
| `POST` | `/copilot/chat` | Ask a question (RAG Q&A) |
| `POST` | `/exam/generate` | Generate practice exam |
| `POST` | `/syllabus/preview` | Parse syllabus PDF |
| `GET` | `/course-summaries/{course_id}` | Course-level summary |
| `GET` | `/knowledge-maps/{course_id}` | Course knowledge map |

### Response envelope (courses, paginated lists)

```jsonc
// Success
{ "status": "success", "message": "OK", "data": { ... } }

// Paginated list
{
  "status": "success",
  "data": [ ... ],
  "pagination": { "total": 42, "page": 1, "page_size": 50, "pages": 1 }
}

// Error
{ "status": "error", "message": "Course not found", "detail": null }
```

### Health check response

```jsonc
// 200 OK — all critical components healthy
{
  "status": "ok",
  "duration_ms": 12,
  "checks": {
    "database":  { "status": "ok" },
    "chromadb":  { "status": "ok" },
    "ollama":    { "status": "ok" }
  }
}

// 503 — critical component down (database or chromadb)
{ "status": "degraded", "checks": { "database": { "status": "error", "detail": "..." } } }
```

---

## Frontend API Client

All backend calls are centralised in [`frontend/lib/api.ts`](frontend/lib/api.ts).
Import the `api` object and call typed methods — no raw `fetch` scattered in components:

```ts
import { api, ApiError } from "@/lib/api"

// List courses (paginated)
const { data: courses, pagination } = await api.courses.list(1, 50)

// Upload a document
const form = new FormData()
form.append("file", file)
form.append("course_id", courseId)
const doc = await api.documents.upload(form)

// Ask a question
const { answer, sources } = await api.copilot.chat({
  question: "מה הגדרת הוצאה מוכרת?",
  course_id: courseId,
})

// Error handling
try {
  await api.courses.delete(courseId)
} catch (err) {
  if (err instanceof ApiError && err.status === 404) {
    // handle not found
  }
}
```

---

## Project Structure

```
learning-copilot/
├── backend/
│   ├── app/
│   │   ├── agents/         # LLM orchestration (QA, summary, knowledge map, exam)
│   │   ├── core/           # logging_config.py, response.py
│   │   ├── db/             # SQLAlchemy engine, session, schema migration
│   │   ├── middleware/     # request_logging.py (per-request trace IDs)
│   │   ├── models/         # ORM models (Course, Document, Summary, Exam …)
│   │   ├── routes/         # FastAPI routers (health, courses, documents, copilot …)
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # vector_store, hybrid_qa_retrieval, pdf_ocr …
│   │   └── main.py         # App factory — middleware, routers, startup
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── components/     # TopNav, ChatWorkspace, Toast, Modal …
│   │   ├── knowledge/      # Knowledge center page
│   │   └── page.tsx        # Home (chat interface)
│   ├── lib/
│   │   └── api.ts          # Central typed API client
│   ├── Dockerfile
│   ├── next.config.ts
│   └── .env.local.example
├── docker-compose.yml
└── README.md
```

---

## Ollama model recommendations

| Model | Params | Speed (CPU) | Use case |
|---|---|---|---|
| `qwen2:0.5b` | 0.5B | 5–15 s | Default — good for most Q&A |
| `llama3.2:1b` | 1.2B | 20–40 s | Better quality, still interactive |
| `phi3:mini` | 3.8B | 90–180 s | High quality, slow on CPU |
| `llama3:latest` | 8B | 120–300 s | Not recommended for interactive use |

Set `OLLAMA_GENERATION_MODEL` and adjust `OLLAMA_GENERATION_TIMEOUT` to match.

---

## Troubleshooting

**Backend won't start — `validate_embeddings_health` fails**
: Ollama is not running or `nomic-embed-text` is not pulled.
  Run `ollama pull nomic-embed-text` and ensure Ollama is reachable at `OLLAMA_BASE_URL`.

**Uploads stuck at "processing"**
: Check backend logs (`LOG_LEVEL=DEBUG`) for the ingestion agent. Common causes: Tesseract not installed, PDF is encrypted, or Ollama embedding timeout.

**Summary stays "pending" forever**
: The background thread failed silently. Set `LOG_LEVEL=DEBUG` and look for `summary_job.*` log lines. Use `POST /documents/{id}/retry-summary` to retry.

**`GET /health` returns 503**
: Check the `checks` object in the response body — it identifies which component is down (`database`, `chromadb`, or `ollama`).

---

## Contributing

1. Fork and create a feature branch
2. Run tests: `cd backend && python -m pytest tests/test_critical_paths.py -q`
3. Open a PR against `main`

---

## Author

Eyal Keren
