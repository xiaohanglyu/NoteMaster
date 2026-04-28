"""Shadow reading pronunciation scoring — Level 1 (Whisper word-match)."""
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WordResult:
    reference: str
    heard: Optional[str]
    status: str  # ok | substituted | omitted | inserted


@dataclass
class ShadowResult:
    overall_score: float
    words: list[WordResult]
    feedback: str


_FEEDBACK_SYSTEM = """You are a pronunciation coach. The user was asked to read a sentence aloud.
Below are the words they got wrong (substituted or omitted). Give brief, specific advice on
each problem word — correct stress, common mistake to avoid. Be encouraging. Max 3 sentences."""


def _normalise(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into words."""
    text = text.lower()
    text = re.sub(r"[^\w\s']", "", text)
    return [w for w in text.split() if w]


def score_shadow_reading(reference: str, transcript: str) -> ShadowResult:
    ref_words = _normalise(reference)
    heard_words = _normalise(transcript)

    if not ref_words:
        return ShadowResult(overall_score=0.0, words=[], feedback="")

    if not heard_words:
        words = [WordResult(reference=w, heard=None, status="omitted") for w in ref_words]
        return ShadowResult(overall_score=0.0, words=words, feedback="")

    matcher = SequenceMatcher(None, ref_words, heard_words, autojunk=False)
    results: list[WordResult] = []
    matched = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for w in ref_words[i1:i2]:
                results.append(WordResult(reference=w, heard=w, status="ok"))
                matched += 1
        elif tag == "replace":
            ref_chunk = ref_words[i1:i2]
            heard_chunk = heard_words[j1:j2]
            for idx, rw in enumerate(ref_chunk):
                hw = heard_chunk[idx] if idx < len(heard_chunk) else None
                results.append(WordResult(reference=rw, heard=hw, status="substituted"))
            for hw in heard_chunk[len(ref_chunk):]:
                results.append(WordResult(reference="", heard=hw, status="inserted"))
        elif tag == "delete":
            for w in ref_words[i1:i2]:
                results.append(WordResult(reference=w, heard=None, status="omitted"))
        elif tag == "insert":
            for w in heard_words[j1:j2]:
                results.append(WordResult(reference="", heard=w, status="inserted"))

    score = round(matched / len(ref_words), 3) if ref_words else 0.0
    return ShadowResult(overall_score=score, words=results, feedback="")


def get_pronunciation_feedback(words: list[WordResult], provider=None) -> str:
    problem = [w for w in words if w.status in ("substituted", "omitted")]
    if not problem:
        return "Perfect pronunciation!"

    lines = []
    for w in problem[:5]:
        if w.status == "substituted":
            lines.append(f"- '{w.reference}' (you said: '{w.heard}')")
        else:
            lines.append(f"- '{w.reference}' (omitted)")

    user_msg = "Problem words:\n" + "\n".join(lines)

    if provider is None:
        from notemaster.ai import _get_provider
        provider = _get_provider()

    return provider.complete(
        _FEEDBACK_SYSTEM,
        [{"role": "user", "content": user_msg}],
        temperature=0.3,
    ).strip()


def assess_shadow(reference: str, transcript: str, provider=None) -> ShadowResult:
    result = score_shadow_reading(reference, transcript)

    if result.overall_score == 1.0:
        result.feedback = "Perfect — every word matched."
        return result

    result.feedback = get_pronunciation_feedback(result.words, provider=provider)
    return result
