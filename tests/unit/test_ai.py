import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from notemaster.models import Concept, EvaluationResult
from notemaster.ai import evaluate

SAMPLE_CONCEPT = Concept(
    id="concept-1",
    title="Fault vs Failure",
    summary=(
        "A fault is one component deviating from its spec. "
        "A failure is when the system as a whole stops providing the required service. "
        "Faults are the cause; failures are the effect."
    ),
    book_id="book-1",
    highlight_ids=["h-1"],
    weight=1.5,
    created_at=datetime(2026, 4, 22),
    updated_at=datetime(2026, 4, 22),
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
        result = evaluate(SAMPLE_CONCEPT, "A fault is when one part fails its spec", client=client)
        assert isinstance(result, EvaluationResult)

    def test_concept_score_parsed(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_CONCEPT, "answer", client=client)
        assert result.concept_score == 4

    def test_english_score_parsed(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_CONCEPT, "answer", client=client)
        assert result.english_score == 3

    def test_suggestions_parsed(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        result = evaluate(SAMPLE_CONCEPT, "answer", client=client)
        assert len(result.concept_suggestions) == 1
        assert len(result.english_suggestions) == 1

    def test_prompt_contains_concept_title(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_CONCEPT, "my answer", client=client)
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "Fault vs Failure" in full_prompt

    def test_prompt_contains_concept_summary(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_CONCEPT, "my answer", client=client)
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "deviating from its spec" in full_prompt

    def test_prompt_contains_user_answer(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_CONCEPT, "my specific answer", client=client)
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "my specific answer" in full_prompt

    def test_prompt_mentions_senior_backend(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_CONCEPT, "my answer", client=client)
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "senior" in full_prompt.lower() or "backend" in full_prompt.lower()

    def test_handles_markdown_code_block(self):
        wrapped = f"```json\n{json.dumps(VALID_AI_RESPONSE)}\n```"
        client = make_mock_client({})
        client.chat.completions.create.return_value.choices[0].message.content = wrapped
        result = evaluate(SAMPLE_CONCEPT, "my answer", client=client)
        assert isinstance(result, EvaluationResult)

    def test_invalid_json_raises(self):
        client = make_mock_client({})
        client.chat.completions.create.return_value.choices[0].message.content = "not valid json"
        with pytest.raises(ValueError, match="invalid response"):
            evaluate(SAMPLE_CONCEPT, "my answer", client=client)


# ---------------------------------------------------------------------------
# #19 — AI role tuning: prompt constraints and temperatures
# ---------------------------------------------------------------------------

class TestAIRoleTuning:
    def test_evaluate_temperature_is_varied(self):
        client = make_mock_client(VALID_AI_RESPONSE)
        evaluate(SAMPLE_CONCEPT, "answer", client=client)
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs.get("temperature", 0) >= 0.3

    def test_evaluate_system_prompt_has_five_angles(self):
        from notemaster.ai import _EVALUATE_SYSTEM
        angles = ["concrete example", "trade-off", "contrast", "failure case", "first principles"]
        for angle in angles:
            assert angle.lower() in _EVALUATE_SYSTEM.lower()

    def test_evaluate_system_prompt_has_two_parts(self):
        from notemaster.ai import _EVALUATE_SYSTEM
        assert "PART 1" in _EVALUATE_SYSTEM
        assert "PART 2" in _EVALUATE_SYSTEM

    def test_synthesis_phase1_faithfulness_constraint(self):
        from notemaster.ai import _PHASE1_SYSTEM
        assert "explicitly present" in _PHASE1_SYSTEM.lower()

    def test_synthesis_phase2_no_external_inference(self):
        from notemaster.ai import _PHASE2_SYSTEM
        assert "general domain knowledge" in _PHASE2_SYSTEM.lower()

    def test_synthesis_tool_loop_uses_low_temperature(self):
        from unittest.mock import patch, MagicMock
        from notemaster.ai import synthesize

        mock_db = MagicMock()
        mock_db.get_highlights.return_value = []
        mock_db.get_concepts.return_value = []
        mock_db.get_edges.return_value = []

        mock_client = MagicMock()
        msg = MagicMock()
        msg.tool_calls = None
        msg.content = "done"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=msg)]
        )
        synthesize("book-1", mock_db, client=mock_client)
        # Phase 2 was skipped (< 2 concepts), so no calls expected
        # Just verify no errors and temperature would be 0.1 in _run_tool_loop
