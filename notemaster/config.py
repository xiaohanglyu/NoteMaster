from dotenv import load_dotenv
import os

load_dotenv()

AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_MODEL = os.getenv("AI_MODEL", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")

# Token budget for the synthesis agentic loop.
# Each batch = highlights that fit in this window.
# Rule of thumb: ~300 tokens/highlight + ~4000 tokens overhead per tool call round.
# At 128k context, keep batches well under 50k to leave room for tool responses.
AI_CONTEXT_WINDOW = int(os.getenv("AI_CONTEXT_WINDOW", "128000"))

# Derived: tokens reserved for prompt + tool schemas + response headroom
_SYNTHESIS_OVERHEAD_TOKENS = 8000
_TOKENS_PER_HIGHLIGHT = 300
_batch_override = os.getenv("SYNTHESIS_BATCH_SIZE")
SYNTHESIS_BATCH_SIZE = (
    int(_batch_override)
    if _batch_override
    else max(5, (AI_CONTEXT_WINDOW - _SYNTHESIS_OVERHEAD_TOKENS) // (_TOKENS_PER_HIGHLIGHT * 4))
)
