#!/bin/bash

set -e

python3 <<'PY'
from pathlib import Path
import sys

def patch_file(path_str, transform):
    path = Path(path_str)
    if not path.exists():
        print(f"ERROR: missing file {path_str}")
        sys.exit(1)
    original = path.read_text()
    backup = path.with_suffix(path.suffix + ".backup.confirmed_bugfix_v2")
    backup.write_text(original)
    updated = transform(original)
    path.write_text(updated)
    print(f"Patched {path_str}")

# --------------------------------------------------
# 1) global_search_service.py
# --------------------------------------------------
def patch_global_search(text: str) -> str:
    old = """        vector_results = vector.search_chunks(
            course_id=course_id,
            query=q,
            top_k=min(5, max(1, limit))
        )

        if vector_results and vector_results.get("documents"):
            docs = vector_results["documents"][0]
            metas = vector_results["metadatas"][0]

            for doc_text, meta in zip(docs, metas):
                results.append({
                    "type": "chunk",
                    "title": meta.get("document_name"),
                    "snippet": _snippet(doc_text),
                    "course_id": meta.get("course_id"),
                    "lecture_id": meta.get("lecture_id"),
                    "document_id": meta.get("document_id"),
                    "document_name": meta.get("document_name"),
                    "chunk_index": meta.get("chunk_index"),
                })"""
    new = """        vector_results = vector.search(
            query=q,
            course_id=course_id,
            lecture_id=None,
            top_k=min(5, max(1, limit))
        )

        for item in vector_results or []:
            results.append({
                "type": "chunk",
                "title": item.get("document_name"),
                "snippet": _snippet(item.get("text", "") or item.get("snippet", "")),
                "course_id": item.get("course_id"),
                "lecture_id": item.get("lecture_id"),
                "document_id": item.get("document_id"),
                "document_name": item.get("document_name"),
                "chunk_index": item.get("chunk_index"),
            })"""
    if old not in text:
        print("WARNING: global_search_service vector block not found")
        return text
    return text.replace(old, new, 1)

# --------------------------------------------------
# 2) documents.py
# --------------------------------------------------
def patch_documents(text: str) -> str:
    # filename validation in _process_single_upload
    old_filename = """    file_extension = file.filename.split(".")[-1].lower()
    saved_file_path = os.path.join(UPLOAD_DIR, file.filename)"""
    new_filename = """    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    safe_filename = os.path.basename(file.filename)
    file_extension = safe_filename.split(".")[-1].lower() if "." in safe_filename else "txt"
    saved_file_path = os.path.join(UPLOAD_DIR, safe_filename)"""
    if old_filename in text:
        text = text.replace(old_filename, new_filename, 1)
    else:
        print("WARNING: documents.py filename block not found")

    old_newdoc = """    new_document = Document(
        course_id=course_id,
        lecture_id=lecture_id,
        file_name=file.filename,"""
    new_newdoc = """    new_document = Document(
        course_id=course_id,
        lecture_id=lecture_id,
        file_name=safe_filename,"""
    if old_newdoc in text:
        text = text.replace(old_newdoc, new_newdoc, 1)
    else:
        print("WARNING: documents.py new_document filename block not found")

    # move ready status to after embeddings
    old_ready = """    doc.language = detected_language
    doc.raw_text = extracted_text
    _set_processing_status(doc, "ready")
    _set_last_error(doc, None)
    db.commit()
    db.refresh(doc)

    vector_store = VectorStoreService()
    try:
      vector_store.delete_by_document_id(doc.id)
    except Exception:
      pass

    vector_store.add_chunks(
        document_id=doc.id,
        course_id=doc.course_id,
        lecture_id=getattr(doc, "lecture_id", None),
        chunks=chunks,
    )

    db.query(Summary).filter(Summary.document_id == doc.id).delete(synchronize_session=False)
    db.commit()"""
    new_ready = """    doc.language = detected_language
    doc.raw_text = extracted_text
    _set_last_error(doc, None)
    db.commit()
    db.refresh(doc)

    vector_store = VectorStoreService()
    try:
      vector_store.delete_by_document_id(doc.id)
    except Exception:
      pass

    vector_store.add_chunks(
        document_id=doc.id,
        course_id=doc.course_id,
        lecture_id=getattr(doc, "lecture_id", None),
        chunks=chunks,
    )

    _set_processing_status(doc, "ready")
    _set_last_error(doc, None)
    db.commit()
    db.refresh(doc)

    db.query(Summary).filter(Summary.document_id == doc.id).delete(synchronize_session=False)
    db.commit()"""
    if old_ready in text:
        text = text.replace(old_ready, new_ready, 1)
    else:
        print("WARNING: documents.py ready-status block not found")

    return text

# --------------------------------------------------
# 3) qa_agent.py
# --------------------------------------------------
def patch_qa_agent(text: str) -> str:
    if "import requests" in text and "from requests import exceptions as requests_exceptions" not in text:
        text = text.replace("import requests\n", "import requests\nfrom requests import exceptions as requests_exceptions\n", 1)

    old = """        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            },
            timeout=180
        )
        response.raise_for_status()
        answer = response.json()["response"]"""
    new = """        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=180
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload.get("response")
            if not answer:
                raise ValueError("Missing 'response' in model reply")
        except (requests_exceptions.ConnectionError, requests_exceptions.Timeout):
            return {
                "answer": "שירות המענה אינו זמין כרגע. נסה שוב בעוד רגע.",
                "sources": []
            }
        except Exception:
            return {
                "answer": "אירעה שגיאה בזמן יצירת התשובה.",
                "sources": []
            }"""
    if old not in text:
        print("WARNING: qa_agent response block not found")
        return text
    return text.replace(old, new, 1)

# --------------------------------------------------
# 4) syllabus.py
# --------------------------------------------------
def patch_syllabus(text: str) -> str:
    if "import os" in text and "import re" not in text:
        text = text.replace("import os\n", "import os\nimport re\n", 1)

    old = """    file_extension = file.filename.split(".")[-1].lower()
    saved_file_path = os.path.join(UPLOAD_DIR, file.filename)"""
    new = """    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    safe_filename = os.path.basename(file.filename)
    safe_filename = re.sub(r"[^A-Za-z0-9._\\-א-ת ]", "_", safe_filename)

    file_extension = safe_filename.split(".")[-1].lower() if "." in safe_filename else "txt"
    saved_file_path = os.path.join(UPLOAD_DIR, safe_filename)"""
    if old in text:
        text = text.replace(old, new, 1)
    else:
        print("WARNING: syllabus.py filename block not found")

    old_return_name = '''        "file_name": file.filename,'''
    new_return_name = '''        "file_name": safe_filename,'''
    if old_return_name in text:
        text = text.replace(old_return_name, new_return_name, 1)
    else:
        print("WARNING: syllabus.py return file_name block not found")

    return text

# --------------------------------------------------
# 5) ai_study_service.py
# --------------------------------------------------
def patch_ai_study(text: str) -> str:
    old = """            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": "You produce strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )

            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            return {
                "summary": data.get("summary", ""),
                "flashcards": data.get("flashcards", []),
                "quiz": data.get("quiz", []),
                "provider": "openai",
            }"""
    new = """            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                temperature=0.2,
                messages=[
                    {"role": "system", "content": "You produce strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )

            if not getattr(response, "choices", None):
                raise ValueError("No choices returned from model")

            first_choice = response.choices[0]
            message = getattr(first_choice, "message", None)
            content = getattr(message, "content", None) or "{}"

            data = json.loads(content)

            return {
                "summary": data.get("summary", ""),
                "flashcards": data.get("flashcards", []),
                "quiz": data.get("quiz", []),
                "provider": "openai",
            }"""
    if old not in text:
        print("WARNING: ai_study_service response block not found")
        return text
    return text.replace(old, new, 1)

# --------------------------------------------------
# 6) copilot.py
# --------------------------------------------------
def patch_copilot(text: str) -> str:
    text = text.replace(
        "from fastapi import APIRouter, Depends, Depends\n",
        "from fastapi import APIRouter, Depends\n"
    )
    return text

patch_file("app/services/global_search_service.py", patch_global_search)
patch_file("app/routes/documents.py", patch_documents)
patch_file("app/agents/qa_agent.py", patch_qa_agent)
patch_file("app/routes/syllabus.py", patch_syllabus)
patch_file("app/services/ai_study_service.py", patch_ai_study)
patch_file("app/routes/copilot.py", patch_copilot)

print("All confirmed bugfixes v2 applied.")
PY
