"""Tests for provider adapters."""
import pytest
from unittest.mock import MagicMock, patch


SYSTEM = "You are a helpful assistant."
MESSAGES = [{"role": "user", "content": "Hello"}]


class TestOpenAICompatibleProvider:
    def test_complete_returns_string(self):
        from notemaster.providers import OpenAICompatibleProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Hello back"))]
        )
        p = OpenAICompatibleProvider(model="gpt-4o", client=mock_client)
        result = p.complete(SYSTEM, MESSAGES, temperature=0.2)
        assert result == "Hello back"

    def test_complete_includes_system_in_messages(self):
        from notemaster.providers import OpenAICompatibleProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )
        p = OpenAICompatibleProvider(model="gpt-4o", client=mock_client)
        p.complete(SYSTEM, MESSAGES, temperature=0.2)
        call_messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert call_messages[0] == {"role": "system", "content": SYSTEM}
        assert call_messages[1:] == MESSAGES

    def test_complete_passes_temperature(self):
        from notemaster.providers import OpenAICompatibleProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )
        p = OpenAICompatibleProvider(model="gpt-4o", client=mock_client)
        p.complete(SYSTEM, MESSAGES, temperature=0.7)
        assert mock_client.chat.completions.create.call_args.kwargs["temperature"] == 0.7

    def test_complete_passes_model(self):
        from notemaster.providers import OpenAICompatibleProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )
        p = OpenAICompatibleProvider(model="llama-3.3-70b", client=mock_client)
        p.complete(SYSTEM, MESSAGES, temperature=0.2)
        assert mock_client.chat.completions.create.call_args.kwargs["model"] == "llama-3.3-70b"

    def test_ping_returns_latency(self):
        from notemaster.providers import OpenAICompatibleProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="pong"))]
        )
        p = OpenAICompatibleProvider(model="gpt-4o", client=mock_client)
        result = p.ping()
        assert result["ok"] is True
        assert "latency_ms" in result

    def test_ping_returns_error_on_failure(self):
        from notemaster.providers import OpenAICompatibleProvider
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("connection refused")
        p = OpenAICompatibleProvider(model="gpt-4o", client=mock_client)
        result = p.ping()
        assert result["ok"] is False
        assert "error" in result


class TestAnthropicProvider:
    def test_complete_returns_string(self):
        from notemaster.providers import AnthropicProvider
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Hello from Claude")]
        )
        p = AnthropicProvider(model="claude-sonnet-4-6", client=mock_client)
        result = p.complete(SYSTEM, MESSAGES, temperature=0.2)
        assert result == "Hello from Claude"

    def test_complete_passes_system_separately(self):
        from notemaster.providers import AnthropicProvider
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="ok")]
        )
        p = AnthropicProvider(model="claude-sonnet-4-6", client=mock_client)
        p.complete(SYSTEM, MESSAGES, temperature=0.2)
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["system"] == SYSTEM
        assert kwargs["messages"] == MESSAGES

    def test_complete_does_not_include_system_in_messages(self):
        from notemaster.providers import AnthropicProvider
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="ok")]
        )
        p = AnthropicProvider(model="claude-sonnet-4-6", client=mock_client)
        p.complete(SYSTEM, MESSAGES, temperature=0.2)
        kwargs = mock_client.messages.create.call_args.kwargs
        roles = [m["role"] for m in kwargs["messages"]]
        assert "system" not in roles

    def test_complete_passes_temperature(self):
        from notemaster.providers import AnthropicProvider
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="ok")]
        )
        p = AnthropicProvider(model="claude-sonnet-4-6", client=mock_client)
        p.complete(SYSTEM, MESSAGES, temperature=0.5)
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["temperature"] == 0.5

    def test_ping_returns_latency(self):
        from notemaster.providers import AnthropicProvider
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="pong")]
        )
        p = AnthropicProvider(model="claude-sonnet-4-6", client=mock_client)
        result = p.ping()
        assert result["ok"] is True
        assert "latency_ms" in result

    def test_ping_returns_error_on_failure(self):
        from notemaster.providers import AnthropicProvider
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("auth failed")
        p = AnthropicProvider(model="claude-sonnet-4-6", client=mock_client)
        result = p.ping()
        assert result["ok"] is False
        assert "error" in result
