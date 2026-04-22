import tempfile
import os
import mlx_whisper
from notemaster.config import WHISPER_MODEL

_MIME_TO_EXT = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}


def transcribe(audio: bytes, mime_type: str) -> str:
    ext = _MIME_TO_EXT.get(mime_type, ".webm")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(audio)
        tmp_path = f.name
    try:
        result = mlx_whisper.transcribe(tmp_path, path_or_hf_repo=f"mlx-community/whisper-{WHISPER_MODEL}-mlx")
        return result["text"].strip()
    finally:
        os.remove(tmp_path)
