# Feature: Multi-Provider AI

**Issue**: #42  
**Status**: In development

---

## Why

Currently the AI backend is hardcoded to a single local endpoint via `.env`.
Switching models requires editing a file and restarting the server. There is
no way to compare quality across providers or use a cloud model when the local
machine is under load.

Target providers:

| Provider | Type | Notes |
|----------|------|-------|
| Local (llama.cpp / Ollama) | OpenAI-compatible | Current default |
| OpenAI (GPT-4o, GPT-4o-mini, …) | OpenAI-compatible | Default base_url |
| Groq (llama-3.3-70b, …) | OpenAI-compatible | Fast inference |
| Anthropic (claude-sonnet-4-6, …) | Anthropic SDK | Different API format |

---

## Architecture

### The problem

All functions in `ai.py` currently call `client.chat.completions.create()` and
read `response.choices[0].message.content`. The Anthropic SDK uses a different
call shape: `client.messages.create()` / `response.content[0].text` and takes
a separate `system` parameter.

Rather than duplicating every function, we introduce a thin **provider
adapter** that exposes a single `complete(system, messages, temperature)`
method and hides the SDK difference behind it.

### Provider adapter (`notemaster/providers.py`)

```python
class BaseProvider:
    def complete(self, system: str, messages: list[dict], temperature: float) -> str: ...

class OpenAICompatibleProvider(BaseProvider):
    # wraps openai.OpenAI with custom base_url
    # works for: local, OpenAI, Groq, Together, Perplexity

class AnthropicProvider(BaseProvider):
    # wraps anthropic.Anthropic
    # converts messages list to Anthropic format
    # passes system as separate kwarg
```

`ai.py` functions are refactored to call
`_get_provider().complete(system, messages, temperature)` instead of
constructing the client directly. The rest of each function (prompt templates,
JSON parsing, validation) is unchanged.

### DB table: `ai_providers`

```sql
CREATE TABLE ai_providers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    provider_type TEXT NOT NULL,   -- 'openai_compatible' | 'anthropic'
    base_url    TEXT,              -- NULL for default OpenAI / Anthropic endpoints
    api_key     TEXT,              -- stored in local DB only, never committed
    model       TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
)
```

Only one row can have `is_active = 1` at a time (enforced in application
layer). On startup the active provider is loaded once; subsequent API calls
use it. Switching provider takes effect immediately without restart.

Fallback chain:
1. Active provider from DB
2. `.env` values (`AI_BASE_URL`, `AI_MODEL`) as an OpenAI-compatible provider
3. Error — no provider configured

---

## API

```
GET    /providers                 list all
POST   /providers                 create
PATCH  /providers/{id}            update name / api_key / model
DELETE /providers/{id}            delete (cannot delete active)
POST   /providers/{id}/activate   set as active provider
POST   /providers/{id}/test       send a minimal ping, return latency + model
```

### `POST /providers` body

```json
{
  "name": "Groq llama-3.3-70b",
  "provider_type": "openai_compatible",
  "base_url": "https://api.groq.com/openai/v1",
  "api_key": "gsk_...",
  "model": "llama-3.3-70b-versatile"
}
```

### `POST /providers/{id}/test` response

```json
{ "ok": true, "latency_ms": 340, "model": "llama-3.3-70b-versatile" }
```

---

## Admin UI

Location: Admin panel → new **AI Providers** section at the top.

Layout:
```
AI Providers                              [+ Add Provider]

● Groq llama-3.3-70b     openai_compatible   [Test] [Edit] [···]   ← active
  Local Gemma 4 26B       openai_compatible   [Test] [Edit] [Activate] [Delete]
  Claude Sonnet 4.6        anthropic           [Test] [Edit] [Activate] [Delete]
```

- Active provider shown with a filled dot and no Activate button
- **Edit** opens inline form for name / api_key / model (base_url read-only after creation)
- **Test** fires `POST /providers/{id}/test`, shows latency or error inline
- **+ Add Provider** opens a form with provider_type selector that shows/hides base_url field

---

## Anthropic message format adapter

Anthropic's API differs from OpenAI's in two ways that matter here:

1. System prompt is a top-level `system=` parameter, not a message with `role: system`
2. Response text is at `response.content[0].text`

The adapter extracts the system message from the list and passes it correctly:

```python
class AnthropicProvider(BaseProvider):
    def complete(self, system, messages, temperature):
        # messages here have role user/assistant only (system already extracted)
        resp = self._client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=4096,
            temperature=temperature,
        )
        return resp.content[0].text
```

---

## Testing strategy

| File | What it covers |
|------|---------------|
| `tests/unit/test_providers.py` | Adapter unit tests — OpenAI-compatible and Anthropic, mocked SDKs |
| `tests/unit/test_providers_db.py` | DB CRUD for ai_providers table |
| `tests/unit/test_providers_api.py` | REST endpoints, activate, test-connection |

All tests mock the underlying SDK clients. No real API keys needed.

---

## Dependencies

- `anthropic` SDK — add to `requirements.txt`
- `openai` SDK already present

---

## Migration

Existing `.env` config continues to work. On first run with this feature, the
DB has no providers, so the fallback reads `AI_BASE_URL` / `AI_MODEL` from
`.env` exactly as before. Users can optionally migrate to DB-backed config at
their own pace.

---

## Acceptance criteria

- [ ] `BaseProvider`, `OpenAICompatibleProvider`, `AnthropicProvider` implemented
- [ ] `ai.py` refactored to use provider adapter (all existing tests still green)
- [ ] `ai_providers` DB table with full CRUD
- [ ] `POST /providers/{id}/activate` switches active provider
- [ ] `POST /providers/{id}/test` returns latency or error
- [ ] Admin UI: list, add, edit, activate, test, delete
- [ ] `.env` fallback still works
- [ ] Full test suite green
