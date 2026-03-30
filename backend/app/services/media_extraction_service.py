import os
import tempfile
from pathlib import Path

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def is_media_file(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS


def get_media_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


class MediaExtractionService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None

        if self.api_key and OpenAI is not None:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception:
                self.client = None

    def transcribe_file(self, file_bytes: bytes, filename: str) -> dict:
        media_type = get_media_type(filename)

        if not is_media_file(filename):
            return {
                "success": False,
                "text": "",
                "media_type": "unknown",
                "provider": "none",
                "error": "Unsupported media file type",
            }

        if self.client is None:
            return {
                "success": True,
                "text": f"[Fallback transcription placeholder] תוכן מתומלל בסיסי עבור הקובץ: {filename}",
                "media_type": media_type,
                "provider": "local_fallback",
                "error": None,
            }

        suffix = Path(filename).suffix.lower()

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            with open(tmp_path, "rb") as media_file:
                transcript = self.client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=media_file,
                )

            text = getattr(transcript, "text", "") or ""

            return {
                "success": True,
                "text": text,
                "media_type": media_type,
                "provider": "openai_transcription",
                "error": None,
            }

        except Exception as e:
            return {
                "success": False,
                "text": "",
                "media_type": media_type,
                "provider": "openai_transcription",
                "error": str(e),
            }
        finally:
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
