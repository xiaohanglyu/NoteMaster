import json
from difflib import SequenceMatcher
from openai import OpenAI
from notemaster.config import AI_BASE_URL, AI_MODEL, SYNTHESIS_BATCH_SIZE
from notemaster.models import Concept, EvaluationResult, Entry, InboxClassification, InboxItem, PronunciationResult
from notemaster.providers import OpenAICompatibleProvider, BaseProvider

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
2. Call create_concept for each group with:
   - summary: built exclusively from the highlight text, written clearly and completely
   - questions: exactly 3 varied review questions a student or interviewer might ask
     about this concept. Cover different angles — e.g. definition, concrete example,
     trade-off, contrast with a related concept, or real-world application.
     Write them as natural English questions.
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
_default_provider: BaseProvider | None = None


def _get_client() -> OpenAI:
    global _default_client
    if _default_client is None:
        _default_client = OpenAI(base_url=AI_BASE_URL, api_key="not-used")
    return _default_client


def _get_provider() -> BaseProvider:
    """Return the active DB provider, or fall back to env-configured local provider."""
    global _default_provider
    try:
        from notemaster.db import Database
        from notemaster.providers import build_provider
        db = Database()
        active = db.get_active_provider()
        if active:
            return build_provider(
                provider_type=active.provider_type,
                model=active.model,
                base_url=active.base_url,
                api_key=active.api_key,
            )
    except Exception:
        pass
    if _default_provider is None:
        _default_provider = OpenAICompatibleProvider(model=AI_MODEL, base_url=AI_BASE_URL)
    return _default_provider


def _provider_from_client(client) -> BaseProvider:
    """Wrap a raw OpenAI client (used in tests) into a provider."""
    return OpenAICompatibleProvider(model=AI_MODEL, client=client)


def evaluate(
    concept: Concept,
    answer: str,
    client=None,
) -> EvaluationResult:
    provider = _provider_from_client(client) if client is not None else _get_provider()
    user_msg = _EVALUATE_USER.format(
        title=concept.title, summary=concept.summary, answer=answer,
    )
    raw = provider.complete(
        _EVALUATE_SYSTEM,
        [{"role": "user", "content": user_msg}],
        temperature=0.4,
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(raw)
        return EvaluationResult(**data)
    except Exception as exc:
        raise ValueError(f"invalid response from AI: {raw!r}") from exc


def synthesize(book_id: str, db, client: OpenAI | None = None, on_progress=None) -> dict:
    """Two-phase synthesis: batched concept creation then edge linking.

    Phase 1: highlights are split into batches of SYNTHESIS_BATCH_SIZE.
             Each batch is a fresh context window — the AI sees the highlights
             inline and calls create_concept / update_concept to persist them.
    Phase 2: a single fresh conversation lists all created concept titles and
             summaries and calls link_concepts to build the edge graph.

    on_progress(phase, batch_current, batch_total, concepts_created, error):
        called after each batch and phase transition.
    """
    from notemaster.tools import SYNTHESIS_TOOLS, ToolHandler

    def _progress(phase, batch_current, batch_total, concepts_created, error=None):
        if on_progress:
            on_progress(phase, batch_current, batch_total, concepts_created, error)

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
    total_batches = max(1, (len(highlights) + SYNTHESIS_BATCH_SIZE - 1) // SYNTHESIS_BATCH_SIZE)
    batch_errors = 0

    for batch_index in range(0, max(1, len(highlights)), SYNTHESIS_BATCH_SIZE):
        batch = highlights[batch_index: batch_index + SYNTHESIS_BATCH_SIZE]
        if not batch:
            break

        batch_num = batch_index // SYNTHESIS_BATCH_SIZE + 1
        batch_text = _format_highlights(batch)
        concepts_so_far = len(db.get_concepts(book_id=book_id))
        _progress("phase1", batch_num, total_batches, concepts_so_far)

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

        try:
            _run_tool_loop(client, messages, phase1_tools, handler)
        except Exception as e:
            batch_errors += 1
            _progress("phase1", batch_num, total_batches,
                      len(db.get_concepts(book_id=book_id)), error=str(e))

    # --- Phase 2: edge creation ---
    concepts = db.get_concepts(book_id=book_id)
    _progress("phase2", 0, 1, len(concepts))

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

        try:
            _run_tool_loop(client, messages, phase2_tools, handler)
        except Exception as e:
            _progress("phase2", 1, 1, len(concepts), error=str(e))

    concepts_final = db.get_concepts(book_id=book_id)
    edges = db.get_edges()
    _progress("done", total_batches, total_batches, len(concepts_final))
    return {"concepts": len(concepts_final), "edges": len(edges), "batch_errors": batch_errors}


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


_EXTRACT_SYSTEM = """\
You are an interview coach. Extract all interview questions and answers from the provided text.
The text may be a transcript, markdown notes, or any informal format.

Rules:
- Extract every distinct question, even if phrased as "Tell me about..." or "Walk me through..."
- For each question, include the answer if one is present in the text; otherwise leave answer empty
- Classify each question:
  - "behavioral" — past experience, STAR stories, "Tell me about a time..."
  - "system_design" — architecture, scalability, design decisions
  - "coding" — algorithms, data structures, implementation
  - "other" — general, culture fit, compensation, etc.
- Do not invent or infer answers beyond what the text contains

Respond ONLY with a JSON array:
[{"question": "...", "answer": "...", "q_type": "behavioral|system_design|coding|other"}, ...]

If no questions are found, return [].
"""


def extract_questions(text: str, client=None) -> list[dict]:
    provider = _provider_from_client(client) if client is not None else _get_provider()
    raw = provider.complete(_EXTRACT_SYSTEM, [{"role": "user", "content": text}], temperature=0.1).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        items = json.loads(raw)
        return [
            {
                "question": item.get("question", ""),
                "answer": item.get("answer", ""),
                "q_type": item.get("q_type", "other"),
            }
            for item in items if item.get("question")
        ]
    except Exception as exc:
        raise ValueError(f"invalid extract response: {raw!r}") from exc


_ENRICH_SYSTEM = """\
You are an English language expert helping a Chinese speaker learn natural English.
Given a word, phrase, or sentence — whether everyday or professional — provide:

1. IPA phonetic transcription (American English)
2. A concise Chinese translation (2–10 characters, native Chinese phrasing)
3. A usage note in this exact format — be specific and practical:
   "[word class] | Context: <domain or register> | When to use: <situation/context> | Pattern: <grammatical pattern with ~>"
   Examples:
   - "noun phrase | Context: mathematics, ML | When to use: measuring straight-line distance between points or vectors | Pattern: calculate/measure the ~ between X and Y"
   - "idiom | Context: professional | When to use: describing a productive start to a new role or project | Pattern: hit the ground running [on/with sth]"
   - "phrasal verb | Context: daily conversation | When to use: saying you almost did something but didn't | Pattern: I was about to ~ when ..."
   - "adjective | Context: informal | When to use: expressing something is fashionable or impressive in casual speech | Pattern: that's so ~"
4. Two natural example sentences matching the actual register (casual if daily, professional if technical)

Respond ONLY with a JSON object:
{
  "phonetics": "<IPA transcription>",
  "translation": "<Chinese translation>",
  "context_note": "<usage note in the format above>",
  "examples": ["<sentence 1>", "<sentence 2>"]
}
"""


def enrich_entry(entry: Entry, client=None) -> dict:
    provider = _provider_from_client(client) if client is not None else _get_provider()
    raw = provider.complete(
        _ENRICH_SYSTEM,
        [{"role": "user", "content": f'Enrich this English expression: "{entry.text}"'}],
        temperature=0.2,
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except Exception as exc:
        raise ValueError(f"invalid enrich response: {raw!r}") from exc


_ENRICH_EXTRA_SYSTEM = """\
You are an English language expert helping a Chinese speaker learn natural English.
Given a word or phrase and a list of requested attributes, provide only those attributes.

Attribute definitions:
- tenses: list of inflected verb forms (e.g. ["run", "runs", "ran", "has run", "will run"])
- word_forms: list of other grammatical forms with label (e.g. ["noun: a run", "adjective: running water"])
- root: etymology string (e.g. "Latin: currere = to run")
- synonyms: list of synonyms with brief contrast note (e.g. ["dash — more sudden", "sprint — short distance"])
- derivatives: list of derived words (e.g. ["runner", "running", "outrun", "forerunner"])

Respond ONLY with a JSON object containing exactly the requested keys.
"""

_EXTRA_FIELD_NAMES = {"tenses", "word_forms", "root", "synonyms", "derivatives"}


def enrich_entry_extra(entry: Entry, fields: list[str], client=None) -> dict:
    if not fields:
        raise ValueError("fields must not be empty")
    provider = _provider_from_client(client) if client is not None else _get_provider()
    field_list = ", ".join(fields)
    raw = provider.complete(
        _ENRICH_EXTRA_SYSTEM,
        [{"role": "user", "content": f'Word/phrase: "{entry.text}"\nRequested attributes: {field_list}'}],
        temperature=0.2,
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        return json.loads(raw)
    except Exception as exc:
        raise ValueError(f"invalid enrich_extra response: {raw!r}") from exc


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


_STUDY_SYSTEM = """\
You are an expert technical interviewer and educator.

Read the article below and generate {count} review questions that cover the key concepts.
Each question must target ONE of these angles (mix them across questions):
- Definition: "What is X and why does it exist?"
- Comparison: "What are the tradeoffs between X and Y?"
- When-to-use: "In what situation would you choose X?"

For each question, write a complete, clear answer (3-5 sentences).
Classify each question as: system_design | coding | other

Respond ONLY with a JSON array — no markdown fences, no extra text:
[{{"question":"...","answer":"...","q_type":"system_design|coding|other"}}]
""".strip()

_INTERVIEW_SYSTEM = """\
You are a senior staff engineer conducting a technical interview.
Your style: scenario-based, never abstract. You probe until you find the boundary of the candidate's knowledge.

Read the article below and generate {count} interview questions.
Rules:
- Frame each question as a real scenario: "You are designing...", "You're on-call and...", "Your team needs..."
- Write a model answer: 3-5 sentences, interview-quality English, concise and precise
- Write 2-3 follow-up probes a senior interviewer would ask after a solid initial answer
- Classify as: system_design | coding | other

Respond ONLY with a JSON array — no markdown fences, no extra text:
[{{"question":"...","answer":"...","q_type":"system_design|coding|other","follow_ups":["...","..."]}}]
""".strip()

_MAX_ARTICLE_CHARS = 12_000


def generate_questions_from_article(
    content: str,
    mode: str = "study",
    count: int = 6,
    client=None,
) -> list[dict]:
    provider = _provider_from_client(client) if client is not None else _get_provider()
    truncated = content[:_MAX_ARTICLE_CHARS]
    system_template = _INTERVIEW_SYSTEM if mode == "interview" else _STUDY_SYSTEM
    system_prompt = system_template.format(count=count)
    raw = provider.complete(system_prompt, [{"role": "user", "content": truncated}], temperature=0.3).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        items = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"invalid generate_questions response: {raw!r}") from exc
    return [
        {
            "question": item.get("question", ""),
            "answer": item.get("answer", ""),
            "q_type": item.get("q_type", "other"),
            "follow_ups": item.get("follow_ups", []),
        }
        for item in items
    ]


_CLASSIFY_SYSTEM = """\
Classify the inbox item into one of: english, concept, question, unknown.
Respond with JSON only — no markdown fences, no extra text:
{
  "item_type": "<english|concept|question|unknown>",
  "reasoning": "<one sentence>",
  "preview": { <structured fields matching the type> }
}

For english: {"text": "...", "translation": "<Chinese>"}
For concept: {"title": "...", "summary": "..."}
For question: {"question": "...", "q_type": "behavioral|system_design|coding|other"}
For unknown: {}""".strip()


def classify_inbox_item(item: InboxItem, client=None) -> InboxClassification:
    provider = _provider_from_client(client) if client is not None else _get_provider()
    raw = provider.complete(
        _CLASSIFY_SYSTEM, [{"role": "user", "content": item.content}], temperature=0.2,
    ).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    return InboxClassification(**data)
