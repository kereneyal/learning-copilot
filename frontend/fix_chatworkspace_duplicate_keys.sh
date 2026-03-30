#!/bin/bash

set -e

FILE="app/components/ChatWorkspace.tsx"

if [ ! -f "$FILE" ]; then
  echo "ERROR: $FILE not found"
  exit 1
fi

BACKUP="${FILE}.backup.$(date +%Y%m%d_%H%M%S)"
cp "$FILE" "$BACKUP"
echo "Backup created: $BACKUP"

python3 <<'PY'
from pathlib import Path
import sys

path = Path("app/components/ChatWorkspace.tsx")
text = path.read_text()

old = 'key={`${item.type}-${item.document_id || item.lecture_id || idx}`}'
new = 'key={`${item.type}-${item.document_id || "no-doc"}-${item.lecture_id || "no-lecture"}-${item.chunk_index ?? idx}`}' 

if old not in text:
    print("ERROR: target key pattern not found")
    sys.exit(1)

text = text.replace(old, new, 1)
path.write_text(text)

print("Patched ChatWorkspace duplicate keys successfully.")
PY

echo ""
echo "Done."
echo "Now run:"
echo "npm run dev"
