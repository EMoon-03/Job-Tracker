"""AI providers for "Fill from a job posting" and the Gmail fallback, with fake SDKs (no network)."""

import dataclasses
import json
import sys
import types

import pytest

from jobtracker import extract
from jobtracker.config import get_settings

POSTING_JSON = {"company": "Orchard AI", "role": "ML Engineer, New Grad", "type": "Full-time", "sector": "Tech",
                "location": "New York, NY", "mode": "Hybrid", "salary": "$140k", "deadline": "2026-12-15",
                "url": "https://example.com/apply", "summary": "Ranking models in PyTorch."}


@pytest.fixture
def fake_sdks(monkeypatch):
    """Install stand-in `anthropic` and `openai` modules that record requests and return canned JSON."""
    calls = []
    reply = {"text": json.dumps(POSTING_JSON)}

    class Anthropic:
        def __init__(self, api_key):
            self.messages = types.SimpleNamespace(create=self._create)

        def _create(self, **kw):
            calls.append(("claude", kw))
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="Here you go:\n" + reply["text"])])

    class OpenAI:
        def __init__(self, api_key):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

        def _create(self, **kw):
            calls.append(("openai", kw))
            msg = types.SimpleNamespace(content=reply["text"])
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=Anthropic))
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))
    return calls, reply


def _settings(**kw):
    base = dict(anthropic_api_key=None, openai_api_key=None, ai_provider="")
    return dataclasses.replace(get_settings(), **{**base, **kw})


def test_no_key_means_no_ai(fake_sdks):
    s = _settings()
    assert extract.provider(s) is None and not extract.is_available(s)
    with pytest.raises(extract.ExtractUnavailable):
        extract.extract_posting("x" * 50, s)
    assert extract.classify_email("subj", "body", s) == {}


def test_provider_choice(fake_sdks):
    assert extract.provider(_settings(openai_api_key="k")) == "openai"
    assert extract.provider(_settings(anthropic_api_key="k")) == "claude"
    both = dict(anthropic_api_key="a", openai_api_key="o")
    assert extract.provider(_settings(**both)) == "claude"                    # Claude first by default
    assert extract.provider(_settings(**both, ai_provider="openai")) == "openai"
    assert extract.provider(_settings(anthropic_api_key="a", ai_provider="openai")) is None  # named one has no key
    assert extract.provider_label(_settings(openai_api_key="k")) == "ChatGPT"


def test_chatgpt_fills_a_posting(fake_sdks):
    calls, _ = fake_sdks
    out = extract.extract_posting("We're hiring an ML engineer...", _settings(openai_api_key="k", openai_model="gpt-test"))
    assert out["company"] == "Orchard AI" and out["deadline"] == "2026-12-15" and out["notes"].startswith("Ranking")
    name, kw = calls[-1]
    assert name == "openai" and kw["model"] == "gpt-test"
    assert kw["response_format"] == {"type": "json_object"}
    assert "JSON" in kw["messages"][0]["content"]                            # json_object mode requires the word


def test_claude_still_works(fake_sdks):
    calls, _ = fake_sdks
    out = extract.extract_posting("posting", _settings(anthropic_api_key="k"))
    assert out["role"] == "ML Engineer, New Grad" and calls[-1][0] == "claude"


def test_gmail_fallback_with_chatgpt(fake_sdks):
    calls, reply = fake_sdks
    reply["text"] = '{"company": "Basalt Data", "role": "Data Engineer"}'
    s = _settings(openai_api_key="k")
    assert extract.classify_email("Thanks for applying", "…", s) == {"company": "Basalt Data", "role": "Data Engineer"}
    reply["text"] = "sorry, no idea"
    assert extract.classify_email("Thanks for applying", "…", s) == {}


def test_config_reports_which_ai(fake_sdks, client, monkeypatch):
    from fastapi.testclient import TestClient

    from jobtracker.main import create_app
    with TestClient(create_app(_settings(openai_api_key="k"))) as c:
        cfg = c.get("/api/config").json()
    assert cfg["extract"] is True and cfg["ai"] == "ChatGPT"
