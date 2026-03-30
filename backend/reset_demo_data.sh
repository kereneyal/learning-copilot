#!/bin/bash

set -e

STAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups/reset_demo_data_$STAMP"

mkdir -p "$BACKUP_DIR"

echo "Creating backups in $BACKUP_DIR ..."

# Backup DB
if [ -f learning_copilot.db ]; then
  cp learning_copilot.db "$BACKUP_DIR/learning_copilot.db.bak"
  echo "Backed up learning_copilot.db"
fi

# Backup uploads
if [ -d storage/uploads ]; then
  mkdir -p "$BACKUP_DIR/storage"
  cp -R storage/uploads "$BACKUP_DIR/storage/uploads.bak"
  echo "Backed up storage/uploads"
fi

# Backup chroma_db
if [ -d chroma_db ]; then
  cp -R chroma_db "$BACKUP_DIR/chroma_db.bak"
  echo "Backed up chroma_db"
fi

echo "Cleaning DB tables..."

python <<'PYEOF'
import sqlite3

conn = sqlite3.connect("learning_copilot.db")
cursor = conn.cursor()

tables_to_clear = [
    "documents",
    "summaries",
    "course_summaries",
    "knowledge_maps"
]

for table in tables_to_clear:
    try:
        cursor.execute(f"DELETE FROM {table}")
        print(f"Cleared table: {table}")
    except Exception as e:
        print(f"Skipped table {table}: {e}")

conn.commit()
conn.close()
PYEOF

echo "Cleaning uploaded files..."

mkdir -p storage/uploads
find storage/uploads -type f -delete

echo "Resetting chroma_db ..."

if [ -d chroma_db ]; then
  rm -rf chroma_db
fi

mkdir -p chroma_db

echo "Demo data reset completed successfully."
echo "Backups saved in: $BACKUP_DIR"
