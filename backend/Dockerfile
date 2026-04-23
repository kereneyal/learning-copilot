# ── Backend Dockerfile ────────────────────────────────────────────────────────
# Multi-stage: "deps" installs Python packages, "runtime" is the final image.
# System dependencies (Tesseract, libGL) are only in the runtime stage.

FROM python:3.11-slim AS deps

WORKDIR /build

# Install build tools needed by some Python packages (e.g., scipy, Pillow).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Tesseract (OCR), libGL (OpenCV / PyMuPDF image rendering).
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-heb \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the deps stage.
COPY --from=deps /install /usr/local

# Copy application source.
COPY . .

# Persistent storage directories — mount as Docker volumes in production.
RUN mkdir -p /app/storage/uploads /app/storage/syllabus /app/chroma_db

EXPOSE 8000

# LOG_FORMAT=text gives readable output in `docker compose logs`.
# Switch to json for log aggregation pipelines (Loki, CloudWatch, etc.).
ENV LOG_FORMAT=text
ENV LOG_LEVEL=INFO

# WEB_CONCURRENCY: keep at 1 while using SQLite + ChromaDB PersistentClient.
# Multiple processes share the same SQLite file and ChromaDB file lock,
# which causes contention under concurrent writes.
# Increase only after migrating to PostgreSQL + ChromaDB HTTP server.
ENV WEB_CONCURRENCY=1

# Use a shell form so $WEB_CONCURRENCY is expanded at container start time.
# (ENV variables are not expanded inside the JSON exec form of CMD.)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}"]
