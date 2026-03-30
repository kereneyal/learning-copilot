#!/bin/bash

set -e

cat > refresh_backfill.py <<'PYEOF'
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.summary import Summary
from app.models.course_summary import CourseSummary
from app.models.knowledge_map import KnowledgeMap

from app.agents.summary_agent import SummaryAgent
from app.agents.course_summary_agent import CourseSummaryAgent
from app.agents.knowledge_map_agent import KnowledgeMapAgent


def main():
    db = SessionLocal()

    try:
        summary_agent = SummaryAgent()
        course_summary_agent = CourseSummaryAgent()
        knowledge_map_agent = KnowledgeMapAgent()

        documents = db.query(Document).all()
        print(f"Found {len(documents)} documents")

        # 1. Create missing document summaries
        created_doc_summaries = 0

        for doc in documents:
            existing_summary = (
                db.query(Summary)
                .filter(Summary.document_id == doc.id)
                .first()
            )

            if existing_summary:
                continue

            if not doc.raw_text or not doc.raw_text.strip():
                print(f"Skipping document {doc.id} - no raw_text")
                continue

            print(f"Creating summary for document: {doc.file_name} ({doc.id})")

            summary_text = summary_agent.summarize(
                doc.raw_text,
                doc.language or "en"
            )

            new_summary = Summary(
                document_id=doc.id,
                summary_text=summary_text,
                language=doc.language or "en"
            )

            db.add(new_summary)
            db.commit()
            created_doc_summaries += 1

        print(f"Created {created_doc_summaries} missing document summaries")

        # 2. Rebuild course summaries for all courses that have summaries
        course_ids = sorted({doc.course_id for doc in documents if doc.course_id})
        print(f"Found {len(course_ids)} courses")

        created_course_summaries = 0
        created_knowledge_maps = 0

        for course_id in course_ids:
            summaries = (
                db.query(Summary)
                .join(Document, Summary.document_id == Document.id)
                .filter(Document.course_id == course_id)
                .all()
            )

            if not summaries:
                print(f"Skipping course {course_id} - no document summaries")
                continue

            summaries_texts = [s.summary_text for s in summaries if s.summary_text]
            if not summaries_texts:
                print(f"Skipping course {course_id} - summaries are empty")
                continue

            language = summaries[0].language or "en"

            print(f"Rebuilding course summary for course: {course_id}")
            course_summary_text = course_summary_agent.summarize_course(
                summaries_texts,
                language
            )

            new_course_summary = CourseSummary(
                course_id=course_id,
                summary_text=course_summary_text,
                language=language
            )

            db.add(new_course_summary)
            db.commit()
            created_course_summaries += 1

            print(f"Rebuilding knowledge map for course: {course_id}")
            knowledge_map_text = knowledge_map_agent.generate_map(
                course_summary=course_summary_text,
                document_summaries=summaries_texts,
                language=language
            )

            new_knowledge_map = KnowledgeMap(
                course_id=course_id,
                map_text=knowledge_map_text,
                language=language
            )

            db.add(new_knowledge_map)
            db.commit()
            created_knowledge_maps += 1

        print("Backfill completed successfully")
        print(f"Document summaries created: {created_doc_summaries}")
        print(f"Course summaries created: {created_course_summaries}")
        print(f"Knowledge maps created: {created_knowledge_maps}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
PYEOF

echo "Running refresh_backfill.py..."
python refresh_backfill.py
echo "Backfill finished."
