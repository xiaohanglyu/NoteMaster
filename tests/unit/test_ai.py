import json
import pytest
from unittest.mock import MagicMock, patch
from notemaster.models import Highlight, HighlightColor, EvaluationResult
from notemaster.ai import evaluate

SAMPLE_HIGHLIGHT = Highlight(
    id="uuid-1",
    text="A fault is defined as one component deviating from its spec",
    color=HighlightColor.GREEN,
    book_title="Designing Data-Intensive Applications",
    chapter="Chapter 1",
)

VALID_AI_RESPONSE = {
    "concept_feedback": "Good understanding of the fault definition.",
    "english_feedback": "Grammar is correct. Expression is clear.",
    "concept_score": 4,
    "english_score": 3,
    "concept_suggestions": ["Mention the difference between fault and failure"],
    "english_suggestions": ["Consider using 'deviates' instead of 'is deviating'"],
}


def make_mock_client(response_json: dict) -> MagicMock:
    message = MagicMock()
    message.content = json.dumps(response_json)
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    return client


class TestEvaluate:
    def test_returns_evaluation_result(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_HIGHLIGHT, "A fault is when one part fails its spec", client=client)
        assert isinstance(result, EvaluationResult)

    def test_concept_score_parsed(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_HIGHLIGHT, "A fault is when one part fails its spec", client=client)
        assert result.concept_score == 4

    def test_english_score_parsed(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_HIGHLIGHT, "A fault is when one part fails its spec", client=client)
        assert result.english_score == 3

    def test_suggestions_parsed(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_HIGHLIGHT, "A fault is when one part fails its spec", client=client)
        assert len(result.concept_suggestions) == 1
        assert len(result.english_suggestions) == 1

    def test_prompt_contains_highlight_text(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_HIGHLIGHT, "my answer", client=client)
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "one component deviating from its spec" in full_prompt

    def test_prompt_contains_user_answer(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_HIGHLIGHT, "my specific answer", client=client)
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "my specific answer" in full_prompt

    def test_prompt_mentions_senior_backend(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_HIGHLIGHT, "my answer", client=client)
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "senior" in full_prompt.lower() or "backend" in full_prompt.lower()

    def test_handles_markdown_code_block(self):
        wrapped = f"```json\n{json.dumps(VALID_AI_RESPONSE)}\n```"
        message = MagicMock()
        message.content = wrapped
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client = MagicMock()
        client.chat.completions.create.return_value = completion
        result = evaluate(SAMPLE_HIGHLIGHT, "my answer", client=client)
        assert isinstance(result, EvaluationResult)

    def test_invalid_json_raises(self):
        message = MagicMock()
        message.content = "not valid json"
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client = MagicMock()
        client.chat.completions.create.return_value = completion
        with pytest.raises(ValueError, match="invalid response"):
            evaluate(SAMPLE_HIGHLIGHT, "my answer", client=client)
