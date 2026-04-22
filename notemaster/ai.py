import json
from openai import OpenAI
from notemaster.config import AI_BASE_URL, AI_MODEL
from notemaster.models import Highlight, EvaluationResult

_SYSTEM_PROMPT = """\
You are an expert technical interviewer and English writing coach.
Your job is to evaluate a senior backend engineer candidate's answer.

Evaluate TWO things simultaneously:
1. CONCEPT: Is the technical explanation accurate and deep enough for a senior backend role?
   Look for: correctness, trade-offs, real-world applicability, concrete examples.
2. ENGLISH: Is the English expression natural, grammatical, and professional?
   Look for: grammar errors, unnatural phrasing, and suggest more native alternatives.

Respond ONLY with a JSON object in this exact format:
{
  "concept_feedback": "<overall concept evaluation in Chinese>",
  "english_feedback": "<overall English evaluation in English>",
  "concept_score": <integer 1-5>,
  "english_score": <integer 1-5>,
  "concept_suggestions": ["<specific suggestion>", ...],
  "english_suggestions": ["<specific suggestion with example>", ...]
}

Scoring guide (1=poor, 3=adequate, 5=excellent):
- concept_score 5: accurate, mentions trade-offs, gives concrete system examples
- english_score 5: native-level fluency, appropriate register, no grammar errors
"""

_USER_TEMPLATE = """\
Book highlight (the concept being tested):
\"\"\"{highlight_text}\"\"\"

Candidate's answer:
\"\"\"{answer}\"\"\"
"""


_default_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _default_client
    if _default_client is None:
        _default_client = OpenAI(base_url=AI_BASE_URL, api_key="not-used")
    return _default_client


def evaluate(
    highlight: Highlight,
    answer: str,
    client: OpenAI | None = None,
) -> EvaluationResult:
    if client is None:
        client = _get_client()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _USER_TEMPLATE.format(
                highlight_text=highlight.text,
                answer=answer,
            ),
        },
    ]

    completion = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
        temperature=0.3,
    )

    raw = completion.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(raw)
        return EvaluationResult(**data)
    except Exception as exc:
        raise ValueError(f"invalid response from AI: {raw!r}") from exc
