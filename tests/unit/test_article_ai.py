import json
import pytest
from unittest.mock import MagicMock


def make_client(payload):
    """Return a mock OpenAI client that returns `payload` as the message content."""
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = payload if isinstance(payload, str) else json.dumps(payload)
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


STUDY_RESPONSE = json.dumps([
    {"question": "What is rate limiting?", "answer": "Rate limiting controls...", "q_type": "system_design"},
    {"question": "Leaky bucket vs token bucket?", "answer": "Token bucket allows bursts...", "q_type": "system_design"},
    {"question": "When would you use REST over GraphQL?", "answer": "REST is simpler...", "q_type": "other"},
    {"question": "What is idempotency?", "answer": "An operation is idempotent...", "q_type": "system_design"},
    {"question": "Explain API versioning strategies.", "answer": "URL, header, and query...", "q_type": "system_design"},
])

INTERVIEW_RESPONSE = json.dumps([
    {
        "question": "You are designing a public API for a fintech startup. How do you handle versioning?",
        "answer": "I would use URL versioning...",
        "q_type": "system_design",
        "follow_ups": ["Why not header versioning?", "What breaks if two teams own the same endpoint?"],
    },
    {
        "question": "Your API is seeing 10x traffic. How do you apply rate limiting?",
        "answer": "I would implement token bucket...",
        "q_type": "system_design",
        "follow_ups": ["How do you handle distributed rate limiting?"],
    },
    {
        "question": "Design a paginated endpoint for a feed with 1M items.",
        "answer": "Cursor-based pagination is preferred...",
        "q_type": "system_design",
        "follow_ups": ["Why not offset-based?", "How does your cursor handle deletions?"],
    },
    {
        "question": "Your API breaks backward compatibility. How do you notify clients?",
        "answer": "Deprecation headers and migration guides...",
        "q_type": "system_design",
        "follow_ups": ["How long is the deprecation window?"],
    },
    {
        "question": "Explain idempotency and why POST requests should sometimes be idempotent.",
        "answer": "Idempotency means multiple calls produce the same result...",
        "q_type": "system_design",
        "follow_ups": ["How do you implement idempotency keys?"],
    },
])


class TestGenerateQuestionsStudyMode:
    def test_returns_list_of_dicts(self):
        from notemaster.ai import generate_questions_from_article
        result = generate_questions_from_article("article content", mode="study", client=make_client(STUDY_RESPONSE))
        assert isinstance(result, list)
        assert len(result) == 5

    def test_each_item_has_required_keys(self):
        from notemaster.ai import generate_questions_from_article
        result = generate_questions_from_article("article content", mode="study", client=make_client(STUDY_RESPONSE))
        for item in result:
            assert "question" in item
            assert "answer" in item
            assert "q_type" in item

    def test_study_mode_no_follow_ups(self):
        from notemaster.ai import generate_questions_from_article
        result = generate_questions_from_article("article content", mode="study", client=make_client(STUDY_RESPONSE))
        for item in result:
            assert item.get("follow_ups", []) == []

    def test_strips_markdown_fences(self):
        from notemaster.ai import generate_questions_from_article
        fenced = f"```json\n{STUDY_RESPONSE}\n```"
        result = generate_questions_from_article("article content", mode="study", client=make_client(fenced))
        assert len(result) == 5

    def test_raises_on_invalid_json(self):
        from notemaster.ai import generate_questions_from_article
        with pytest.raises((ValueError, Exception)):
            generate_questions_from_article("article content", mode="study", client=make_client("not json"))


class TestGenerateQuestionsInterviewMode:
    def test_returns_list(self):
        from notemaster.ai import generate_questions_from_article
        result = generate_questions_from_article("article content", mode="interview", client=make_client(INTERVIEW_RESPONSE))
        assert isinstance(result, list)
        assert len(result) == 5

    def test_interview_items_have_follow_ups(self):
        from notemaster.ai import generate_questions_from_article
        result = generate_questions_from_article("article content", mode="interview", client=make_client(INTERVIEW_RESPONSE))
        for item in result:
            assert "follow_ups" in item
            assert isinstance(item["follow_ups"], list)
            assert len(item["follow_ups"]) >= 1

    def test_interview_mode_sends_different_prompt(self):
        from notemaster.ai import generate_questions_from_article
        client = make_client(INTERVIEW_RESPONSE)
        generate_questions_from_article("article content", mode="interview", client=client)
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else call_args.kwargs["messages"]
        system_content = next(m["content"] for m in messages if m["role"] == "system")
        assert "scenario" in system_content.lower() or "interview" in system_content.lower()

    def test_study_mode_sends_different_prompt_than_interview(self):
        from notemaster.ai import generate_questions_from_article
        study_client = make_client(STUDY_RESPONSE)
        interview_client = make_client(INTERVIEW_RESPONSE)
        generate_questions_from_article("content", mode="study", client=study_client)
        generate_questions_from_article("content", mode="interview", client=interview_client)
        study_sys = next(
            m["content"]
            for m in study_client.chat.completions.create.call_args.kwargs["messages"]
            if m["role"] == "system"
        )
        interview_sys = next(
            m["content"]
            for m in interview_client.chat.completions.create.call_args.kwargs["messages"]
            if m["role"] == "system"
        )
        assert study_sys != interview_sys
