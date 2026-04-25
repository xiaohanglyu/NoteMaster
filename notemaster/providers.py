"""AI provider adapters — unified complete() interface over OpenAI and Anthropic SDKs."""
import time


class BaseProvider:
    model: str

    def complete(self, system: str, messages: list[dict], temperature: float = 0.2) -> str:
        raise NotImplementedError

    def ping(self) -> dict:
        start = time.monotonic()
        try:
            self.complete("ping", [{"role": "user", "content": "ping"}], temperature=0.0)
            latency_ms = round((time.monotonic() - start) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "model": self.model}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "model": self.model}


class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, model: str, base_url: str | None = None, api_key: str = "not-used", client=None):
        self.model = model
        if client is not None:
            self._client = client
        else:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=base_url,
                api_key=api_key,
            )

    def complete(self, system: str, messages: list[dict], temperature: float = 0.2) -> str:
        full_messages = [{"role": "system", "content": system}] + list(messages)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
        )
        return response.choices[0].message.content


class AnthropicProvider(BaseProvider):
    def __init__(self, model: str, api_key: str | None = None, client=None):
        self.model = model
        if client is not None:
            self._client = client
        else:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, messages: list[dict], temperature: float = 0.2) -> str:
        response = self._client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=4096,
            temperature=temperature,
        )
        return response.content[0].text


def build_provider(provider_type: str, model: str, base_url: str | None = None, api_key: str | None = None) -> BaseProvider:
    if provider_type == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    return OpenAICompatibleProvider(model=model, base_url=base_url, api_key=api_key or "not-used")
