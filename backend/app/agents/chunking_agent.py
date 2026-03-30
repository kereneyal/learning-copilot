import re


class ChunkingAgent:
    def __init__(self, max_chunk_size: int = 1200, overlap_size: int = 200):
        self.max_chunk_size = max_chunk_size
        self.overlap_size = overlap_size

    def clean_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def split_paragraphs(self, text: str):
        text = self.clean_text(text)
        if not text:
            return []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return paragraphs

    def chunk_text(self, text: str):
        paragraphs = self.split_paragraphs(text)

        if not paragraphs:
            return []

        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            candidate = paragraph if not current_chunk else current_chunk + "\n\n" + paragraph

            if len(candidate) <= self.max_chunk_size:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                if len(paragraph) <= self.max_chunk_size:
                    current_chunk = paragraph
                else:
                    long_parts = self._split_long_paragraph(paragraph)
                    for i, part in enumerate(long_parts):
                        if i < len(long_parts) - 1:
                            chunks.append(part.strip())
                        else:
                            current_chunk = part

        if current_chunk:
            chunks.append(current_chunk.strip())

        return self._add_overlap(chunks)

    def _split_long_paragraph(self, paragraph: str):
        sentences = re.split(r'(?<=[.!?։׃])\s+', paragraph)
        parts = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = sentence if not current else current + " " + sentence

            if len(candidate) <= self.max_chunk_size:
                current = candidate
            else:
                if current:
                    parts.append(current.strip())

                if len(sentence) <= self.max_chunk_size:
                    current = sentence
                else:
                    forced_parts = self._force_split(sentence)
                    parts.extend(forced_parts[:-1])
                    current = forced_parts[-1]

        if current:
            parts.append(current.strip())

        return parts

    def _force_split(self, text: str):
        parts = []
        start = 0

        while start < len(text):
            end = start + self.max_chunk_size
            chunk = text[start:end].strip()
            if chunk:
                parts.append(chunk)
            start = end

        return parts

    def _add_overlap(self, chunks):
        if not chunks or self.overlap_size <= 0:
            return chunks

        overlapped = []

        for i, chunk in enumerate(chunks):
            if i == 0:
                overlapped.append(chunk)
                continue

            prev = overlapped[-1]
            overlap = prev[-self.overlap_size:] if len(prev) > self.overlap_size else prev
            merged = (overlap + "\n\n" + chunk).strip()
            overlapped.append(merged)

        return overlapped
