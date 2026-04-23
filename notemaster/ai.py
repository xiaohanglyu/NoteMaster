import json
from difflib import SequenceMatcher
from openai import OpenAI
from notemaster.config import AI_BASE_URL, AI_MODEL, SYNTHESIS_BATCH_SIZE
from notemaster.models import Concept, EvaluationResult, Entry, PronunciationResult

_EVALUATE_SYSTEM = """\
You are a senior backend engineering interviewer and English writing coach.

Your role has two parts:

PART 1 — ACCURACY CHECK (strict)
Evaluate whether the candidate's answer is technically correct, anchored to the
reference description below. Penalise omissions, misconceptions, or vague hand-waving.
Do not give credit for claims that cannot be supported by the reference.

PART 2 — ANGLE (vary each session, pick ONE):
Choose the lens that best fits this concept and probe it in your feedback:
- Concrete example: did the candidate ground the concept in a real system or scenario?
- Trade-off: did the candidate address limitations, costs, or when NOT to use this?
- Contrast: did the candidate distinguish this from a closely related concept?
- Failure case: did the candidate recognise when or why this approach breaks down?
- First principles: could someone with no prior knowledge follow the explanation?

Evaluate BOTH concept depth (Part 1 + chosen angle) and English expression quality.

Respond ONLY with a JSON object in this exact format:
{
  "concept_feedback": "<evaluation in Chinese — state which angle you used, then assess accuracy and depth>",
  "english_feedback": "<evaluation in English — grammar, naturalness, register>",
  "concept_score": <integer 1-5>,
  "english_score": <integer 1-5>,
  "concept_suggestions": ["<specific suggestion tied to the chosen angle>", ...],
  "english_suggestions": ["<specific suggestion with a corrected example>", ...]
}

Scoring guide (1=poor, 3=adequate, 5=excellent):
- concept_score 5: accurate, covers the chosen angle fully, concrete and precise
- english_score 5: native-level fluency, appropriate register, no grammar errors
"""

_EVALUATE_USER = """\
Concept: {title}

Reference description (ground truth — do not go beyond this):
\"\"\"{summary}\"\"\"

Candidate's answer:
\"\"\"{answer}\"\"\"
"""

_PHASE1_SYSTEM = """\
You are a knowledge graph architect. Your sole job is to faithfully organise
information from book highlights into concept nodes.

STRICT RULE: Only use information explicitly present in the provided highlights.
Do not introduce external knowledge, background context, analogies, or facts that
cannot be traced directly back to the source text. If a highlight is ambiguous,
reflect that ambiguity in the summary — do not resolve it with outside knowledge.

Your task:
1. Group semantically related highlights into concepts
2. Call create_concept for each group — the summary must be built exclusively
   from the highlight text, written clearly and completely
3. Every highlight in this batch must be assigned to exactly one concept

Guidelines:
- Prefer fewer, richer concepts over many narrow ones
- Summaries should be self-contained for review, but faithful to the source
"""

_PHASE2_SYSTEM = """\
You are a knowledge graph editor. Your job is to identify relationships between
the concepts listed below — based only on what the concept summaries state.

Do not infer relationships from general domain knowledge. Only create an edge
if the relationship is clearly supported by the concept summaries themselves.

Call link_concepts for each relationship you find.
Relation types:
- depends_on: from_concept requires understanding of to_concept
- contrasts_with: the two concepts differ in a meaningful way
- part_of: from_concept is a component of to_concept
- example_of: from_concept is a concrete instance of to_concept
"""


_default_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _default_client
    if _default_client is None:
        _default_client = OpenAI(base_url=AI_BASE_URL, api_key="not-used")
    return _default_client


def evaluate(
    concept: Concept,
    answer: str,
    client: OpenAI | None = None,
) -> EvaluationResult:
    if client is None:
        client = _get_client()

    messages = [
        {"role": "system", "content": _EVALUATE_SYSTEM},
        {
            "role": "user",
            "content": _EVALUATE_USER.format(
                title=concept.title,
                summary=concept.summary,
                answer=answer,
            ),
        },
    ]

    completion = client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
        temperature=0.4,
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


def synthesize(book_id: str, db, client: OpenAI | None = None) -> dict:
    """Two-phase synthesis: batched concept creation then edge linking.

    Phase 1: highlights are split into batches of SYNTHESIS_BATCH_SIZE.
             Each batch is a fresh context window — the AI sees the highlights
             inline and calls create_concept / update_concept to persist them.
    Phase 2: a single fresh conversation lists all created concept titles and
             summaries and calls link_concepts to build the edge graph.
    """
    from notemaster.tools import SYNTHESIS_TOOLS, ToolHandler

    if client is None:
        client = _get_client()

    handler = ToolHandler(db)

    phase1_tools = [
        t for t in SYNTHESIS_TOOLS
        if t["function"]["name"] in ("create_concept", "update_concept")
    ]
    phase2_tools = [
        t for t in SYNTHESIS_TOOLS
        if t["function"]["name"] == "link_concepts"
    ]

    # --- Phase 1: batched concept extraction ---
    highlights = db.get_highlights(book_id=book_id, unprocessed_only=True)

    for batch_index in range(0, max(1, len(highlights)), SYNTHESIS_BATCH_SIZE):
        batch = highlights[batch_index: batch_index + SYNTHESIS_BATCH_SIZE]
        if not batch:
            break

        batch_num = batch_index // SYNTHESIS_BATCH_SIZE + 1
        total_batches = (len(highlights) + SYNTHESIS_BATCH_SIZE - 1) // SYNTHESIS_BATCH_SIZE
        batch_text = _format_highlights(batch)

        messages = [
            {"role": "system", "content": _PHASE1_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Book ID: {book_id}\n"
                    f"Batch {batch_num}/{total_batches} "
                    f"({len(batch)} highlights)\n\n"
                    f"{batch_text}\n\n"
                    "Group these highlights into concepts and call create_concept for each group."
                ),
            },
        ]

        _run_tool_loop(client, messages, phase1_tools, handler)

    # --- Phase 2: edge creation ---
    concepts = db.get_concepts(book_id=book_id)
    if len(concepts) >= 2:
        concepts_text = _format_concepts(concepts)

        messages = [
            {"role": "system", "content": _PHASE2_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Book ID: {book_id}\n"
                    f"Concepts ({len(concepts)} total):\n\n"
                    f"{concepts_text}\n\n"
                    "Call link_concepts for each meaningful relationship between these concepts."
                ),
            },
        ]

        _run_tool_loop(client, messages, phase2_tools, handler)

    concepts_final = db.get_concepts(book_id=book_id)
    edges = db.get_edges()
    return {"concepts": len(concepts_final), "edges": len(edges)}


def _run_tool_loop(
    client: OpenAI,
    messages: list[dict],
    tools: list[dict],
    handler,
) -> None:
    """Drive the LLM tool-use loop until it stops calling tools."""
    while True:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )

        msg = response.choices[0].message
        assistant_turn: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if not msg.tool_calls:
            break

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = handler.dispatch(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })


_ENRICH_SYSTEM = """\
You are an English language expert helping a Chinese speaker learn natural English.
Given a word, phrase, or sentence — whether everyday or professional — provide:

1. IPA phonetic transcription (American English)
2. A usage note in this exact format — be specific and practical:
   "[word class] | Context: <domain or register> | When to use: <situation/context> | Pattern: <grammatical pattern with ~>"
   Examples:
   - "noun phrase | Context: mathematics, ML | When to use: measuring straight-line distance between points or vectors | Pattern: calculate/measure the ~ between X and Y"
   - "idiom | Context: professional | When to use: describing a productive start to a new role or project | Pattern: hit the ground running [on/with sth]"
   - "phrasal verb | Context: daily conversation | When to use: saying you almost did something but didn't | Pattern: I was about to ~ when ..."
   - "adjective | Context: informal | When to use: expressing something is fashionable or impressive in casual speech | Pattern: that's so ~"
3. Two natural example sentences matching the actual register (casual if daily, professional if technical)

Respond ONLY with a JSON object:
{
  "phonetics": "<IPA transcription>",
  "context_note": "<usage note in the format above>",
  "examples": ["<sentence 1>", "<sentence 2>"]
}
"""


def enrich_entry(entry: Entry, client: OpenAI | None = None) -> dict:
    if client is None:
        client = _get_client()

    completion = client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": _ENRICH_SYSTEM},
            {"role": "user", "content": f'Enrich this English expression: "{entry.text}"'},
        ],
        temperature=0.2,
    )

    raw = completion.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except Exception as exc:
        raise ValueError(f"invalid enrich response: {raw!r}") from exc


def check_pronunciation(entry: Entry, transcript: str) -> PronunciationResult:
    heard = transcript.strip()
    score = SequenceMatcher(None, entry.text.lower(), heard.lower()).ratio()
    return PronunciationResult(heard=heard, match=score >= 0.8, score=round(score, 2))


def _format_highlights(highlights) -> str:
    lines = []
    for h in highlights:
        line = f"[{h.id}] ({h.color.value}) {h.text}"
        if h.chapter:
            line += f"  [chapter: {h.chapter}]"
        lines.append(line)
    return "\n".join(lines)


def _format_concepts(concepts) -> str:
    lines = []
    for c in concepts:
        lines.append(f"[{c.id}] {c.title}\n  {c.summary}")
    return "\n\n".join(lines)
