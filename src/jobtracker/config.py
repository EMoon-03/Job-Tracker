"""Settings, read from the environment and from env files.

Env files, first match wins for each setting:
  1. $JOBTRACKER_ENV, if set
  2. ./.env in the current directory
  3. the settings file `jobtracker install` writes: ~/.config/jobtracker/env, or %APPDATA%\\jobtracker\\env on Windows
  4. the project's .env when running from a checkout
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    anthropic_api_key: str | None
    claude_model: str
    host: str
    port: int
    gmail_address: str | None = None
    gmail_app_password: str | None = None
    gmail_imap_host: str = "imap.gmail.com"
    gmail_since: dt.date | None = None
    demo_mode: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-luna"
    ai_provider: str = ""          # "claude", "openai", or "" = whichever has a key (Claude first)
    password: str | None = None
    repo_url: str = ""


def config_dir() -> Path:
    """~/.config/jobtracker on Linux/macOS, %APPDATA%\\jobtracker on Windows ($XDG_CONFIG_HOME wins if set)."""
    if os.getenv("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "jobtracker"
    if sys.platform == "win32" and os.getenv("APPDATA"):
        return Path(os.environ["APPDATA"]) / "jobtracker"
    return Path.home() / ".config" / "jobtracker"


def env_files() -> list[Path]:
    files = [Path(os.environ["JOBTRACKER_ENV"])] if os.getenv("JOBTRACKER_ENV") else []
    return files + [Path.cwd() / ".env", config_dir() / "env"]


def get_settings() -> Settings:
    for f in env_files():
        if f.is_file():
            load_dotenv(f, override=False)
    load_dotenv(override=False)
    return Settings(
        # Default: local Unix socket, current OS user, database "jobtracker".
        # Windows has no Unix socket; set DATABASE_URL there (see README).
        database_url=os.getenv("DATABASE_URL", "postgresql:///jobtracker"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        claude_model=os.getenv("JOBTRACKER_CLAUDE_MODEL", "claude-haiku-5-5"),
        host=os.getenv("JOBTRACKER_HOST", "127.0.0.1"),
        # Hosts like Render set PORT; JOBTRACKER_PORT wins if both are set.
        port=int(os.getenv("JOBTRACKER_PORT") or os.getenv("PORT") or "8765"),
        gmail_address=(os.getenv("GMAIL_ADDRESS") or "").strip() or None,
        gmail_app_password=(os.getenv("GMAIL_APP_PASSWORD") or "").strip() or None,
        gmail_imap_host=os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com"),
        gmail_since=_date(os.getenv("GMAIL_SYNC_SINCE")),
        demo_mode=_flag(os.getenv("JOBTRACKER_DEMO")),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("JOBTRACKER_OPENAI_MODEL", "gpt-6-luna"),
        ai_provider=(os.getenv("JOBTRACKER_AI") or "").strip().lower(),
        password=os.getenv("JOBTRACKER_PASSWORD") or None,
        repo_url=(os.getenv("JOBTRACKER_REPO_URL") or "").strip(),
    )


def _flag(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _date(v: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(v.strip()) if v and v.strip() else None
    except ValueError:
        return None
