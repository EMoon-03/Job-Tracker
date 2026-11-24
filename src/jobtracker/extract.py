"""Optional AI help: fill an application from a pasted job posting, and name the company in emails the
Gmail rules can't place. Works with Claude (Anthropic API) or ChatGPT (OpenAI API), whichever has a key."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Settings

TYPES = {"Internship", "Full-time", "Part-time", "Co-op", "Contract"}
SECTORS = {"Finance", "Consulting", "Defense", "Tech", "Government", "Other"}
MODES = {"On-site", "Hybrid", "Remote"}

PROMPT = """Extract details from this job posting for a job-application tracker.
Return ONLY a JSON object with these keys:
- "company": employer name
- "role": job title as posted
- "type": one of "Internship","Full-time","Part-time","Co-op","Contract", or ""
- "sector": one of "Finance","Consulting","Defense","Tech","Government","Other" (banks/fintech/insurance = Finance; aerospace/military contractors = Defense)
- "location": city and state, or "Remote"
- "mode": one of "On-site","Hybrid","Remote", or ""
- "salary": pay as stated (e.g. "$40-48/hr"), or ""
- "deadline": application deadline as YYYY-MM-DD, or "" (today is {today})
- "url": application link if one appears in the text, or ""
- "summary": one plain sentence (max 30 words) on what the role works on and the key skills asked for
Use "" for anything not stated. Do not invent details.

POSTING:
\"\"\"
{posting}
\"\"\""""


class ExtractUnavailable(RuntimeError):
    pass


PROVIDERS = {"claude": ("anthropic", "Claude"), "openai": ("openai", "ChatGPT")}


def _installed(module: str) -> bool:
    try:
        __import__(module)
    except ImportError:
        return False
    return True


def provider(settings: "Settings") -> str | None:
    """Which AI to use: the one JOBTRACKER_AI names, else whichever has a key (Claude first). None if neither works."""
    keys = {"claude": settings.anthropic_api_key, "openai": settings.openai_api_key}
    order = [settings.ai_provider] if settings.ai_provider in PROVIDERS else ["claude", "openai"]
    for name in order:
        if keys[name] and _installed(PROVIDERS[name][0]):
            return name
    return None


def provider_label(settings: "Settings") -> str | None:
    name = provider(settings)
    return PROVIDERS[name][1] if name else None


def is_available(settings: "Settings") -> bool:
    return provider(settings) is not None


def _ask(prompt: str, settings: "Settings", max_tokens: int) -> dict:
    """Send one prompt that asks for a JSON object; return the parsed object."""
    name = provider(settings)
    if name == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(model=settings.claude_model, max_tokens=max_tokens,
                                     messages=[{"role": "user", "content": prompt}])
        reply = "".join(getattr(b, "text", "") for b in msg.content)
    elif name == "openai":
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            reasoning_effort="low",                 # a lookup task; keep it quick and cheap
            max_completion_tokens=max_tokens * 4,   # room for reasoning tokens
        )
        reply = resp.choices[0].message.content or ""
    else:
        raise ExtractUnavailable("Set ANTHROPIC_API_KEY or OPENAI_API_KEY (and install that extra) to use this.")
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        raise ValueError(f"{PROVIDERS[name][1]} didn't return JSON")
    return json.loads(m.group(0))


def clean(raw: dict) -> dict:
    """Keep only known keys with sane values."""
    out: dict[str, str] = {}
    for k in ("company", "role", "location", "salary"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:200]
    if raw.get("type") in TYPES:
        out["type"] = raw["type"]
    if raw.get("sector") in SECTORS:
        out["sector"] = raw["sector"]
    if raw.get("mode") in MODES:
        out["mode"] = raw["mode"]
    d = raw.get("deadline")
    if isinstance(d, str):
        try:
            out["deadline"] = dt.date.fromisoformat(d).isoformat()
        except ValueError:
            pass
    u = raw.get("url")
    if isinstance(u, str) and re.match(r"^https?://", u):
        out["url"] = u[:2000]
    s = raw.get("summary")
    if isinstance(s, str) and s.strip():
        out["notes"] = s.strip()[:600]
    return out


def extract_posting(text: str, settings: "Settings") -> dict:
    prompt = PROMPT.format(today=dt.date.today().isoformat(), posting=text[:15000])
    return clean(_ask(prompt, settings, max_tokens=800))


CLASSIFY_PROMPT = """This email is about a job application. Name the hiring company (not the job board or
applicant-tracking system that sent it) and the role title.
Return ONLY a JSON object: {{"company": "...", "role": "..."}}. Use "" for anything not stated.

Subject: {subject}

{body}"""


def classify_email(subject: str, body: str, settings: "Settings") -> dict:
    """Fallback used by the Gmail sync when the rules can't tell which company an email is from."""
    if not is_available(settings):
        return {}
    try:
        raw = _ask(CLASSIFY_PROMPT.format(subject=subject[:300], body=body[:4000]), settings, max_tokens=200)
    except ValueError:
        return {}
    return {k: str(raw.get(k, ""))[:200].strip() for k in ("company", "role")}
