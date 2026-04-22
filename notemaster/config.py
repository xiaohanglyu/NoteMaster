from dotenv import load_dotenv
import os

load_dotenv()

AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_MODEL = os.getenv("AI_MODEL", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
