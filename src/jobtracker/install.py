"""`jobtracker install` / `restart` / `uninstall`: run in the background, start on login, add a launcher entry.

Linux: a systemd user service plus a .desktop entry for your app launcher.
Windows: the windowless `jobtracker-bg.exe` in your sign-in programs (HKCU Run key) plus a
Start-menu shortcut. Neither needs admin rights.

Also creates the local database on first use, so a fresh machine needs no `createdb`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from .config import Settings, config_dir

SERVICE = "jobtracker.service"
WINDOWS = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "JobTracker"

ENV_TEMPLATE = """\
# Job Tracker settings. Restart after editing: jobtracker restart

# Database. Linux default: local PostgreSQL over the Unix socket, as your user.
# On Windows set it, e.g. DATABASE_URL=postgresql://postgres:postgres@localhost:5432/jobtracker
# DATABASE_URL=postgresql:///jobtracker

# Gmail sync (Google Account > Security > App passwords)
# GMAIL_ADDRESS=you@gmail.com
# GMAIL_APP_PASSWORD=abcd efgh ijkl mnop

# Optional AI help for "Fill from a job posting" and the Gmail fallback: Claude or ChatGPT.
# Install the matching extra first: uv tool install '.[claude]' --reinstall   (or '.[openai]')
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# JOBTRACKER_AI=openai    (only needed if both keys are set; Claude is the default)

# JOBTRACKER_PORT=8765
"""


def ensure_database(url: str) -> bool:
    """Create the database if the server is reachable but the database doesn't exist yet.

    Returns True if it created one. Any other connection problem is left for the caller to report.
    """
    try:
        psycopg.connect(url, connect_timeout=5).close()
        return False
    except psycopg.OperationalError as e:
        if "does not exist" not in str(e):
            return False
    name = conninfo_to_dict(url).get("dbname")
    if not name:
        return False
    try:
        with psycopg.connect(make_conninfo(url, dbname="postgres"), autocommit=True, connect_timeout=5) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    except psycopg.Error:
        return False
    return True


def _exe() -> str:
    """Absolute path of the `jobtracker` command that's running now (kept as a symlink path, so upgrades apply)."""
    found = shutil.which(sys.argv[0]) or shutil.which("jobtracker")
    return os.path.abspath(found or sys.argv[0])


def _data_home() -> Path:
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def unit_path() -> Path:
    return config_dir().parent / "systemd" / "user" / SERVICE


def desktop_path() -> Path:
    return _data_home() / "applications" / "jobtracker.desktop"


def unit_text(exe: str) -> str:
    return f"""[Unit]
Description=Job Tracker
After=network.target

[Service]
ExecStart={exe} serve
# PostgreSQL is a system service, so keep retrying until it's up.
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def desktop_text(port: int) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Job Tracker
Comment=Track job applications
Exec=xdg-open http://localhost:{port}
Icon=x-office-calendar
Categories=Office;
Keywords=jobs;applications;tracker;
"""


def _systemctl(*args: str) -> bool:
    if not shutil.which("systemctl"):
        return False
    return subprocess.run(["systemctl", "--user", *args], check=False).returncode == 0


def log_path() -> Path:
    """Where the background app writes its output on Windows (Linux uses the systemd journal)."""
    if WINDOWS and os.getenv("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "jobtracker" / "jobtracker.log"
    return Path(os.getenv("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "jobtracker" / "jobtracker.log"


def _write_settings() -> str:
    env = config_dir() / "env"
    if env.exists():
        return f"Settings: {env} (kept)"
    env.parent.mkdir(parents=True, exist_ok=True)
    local = Path.cwd() / ".env"
    env.write_text(local.read_text("utf-8") if local.is_file() else ENV_TEMPLATE, "utf-8")
    env.chmod(0o600)  # may hold your Gmail app password (on Windows this only clears read-only)
    return f"Settings: {env}" + (" (copied from ./.env)" if local.is_file() else "")


def install(s: Settings, start: bool = True) -> list[str]:
    """Write the settings file (if missing), create the database, set up start-on-login. Returns messages."""
    msgs = [_write_settings()]
    if ensure_database(s.database_url):
        msgs.append("Created the database.")
    return msgs + (_install_windows(s, start) if WINDOWS else _install_linux(s, start))


def restart(s: Settings) -> list[str]:
    if WINDOWS:
        _stop_windows()
        return _start_windows(s)
    if _systemctl("restart", SERVICE):
        return [f"Restarted: http://localhost:{s.port}"]
    return ["Couldn't restart. Is it installed? Run: jobtracker install"]


def uninstall() -> list[str]:
    return _uninstall_windows() if WINDOWS else _uninstall_linux()


# ---- Linux: systemd user service + .desktop entry

def _install_linux(s: Settings, start: bool) -> list[str]:
    msgs = []
    unit = unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(unit_text(_exe()), "utf-8")
    desk = desktop_path()
    desk.parent.mkdir(parents=True, exist_ok=True)
    desk.write_text(desktop_text(s.port), "utf-8")
    msgs.append(f"Launcher entry: {desk}")

    if start and _systemctl("daemon-reload") and _systemctl("enable", "--now", SERVICE):
        msgs.append(f"Running now and on every login: http://localhost:{s.port}")
    else:
        msgs.append(f"Service written to {unit}. Start it with: systemctl --user enable --now jobtracker")
    return msgs


def _uninstall_linux() -> list[str]:
    _systemctl("disable", "--now", SERVICE)
    removed = [str(p) for p in (unit_path(), desktop_path()) if p.exists()]
    for p in (unit_path(), desktop_path()):
        p.unlink(missing_ok=True)
    _systemctl("daemon-reload")
    return [f"Removed {p}" for p in removed] + [
        f"Kept your settings ({config_dir() / 'env'}) and your database."]


# ---- Windows: sign-in Run key + Start-menu shortcut, using the windowless jobtracker-bg.exe

def _winreg():
    import winreg  # only exists on Windows; tests swap in a fake
    return winreg


def _bg_exe() -> str | None:
    sibling = Path(_exe()).with_name("jobtracker-bg.exe")
    return str(sibling) if sibling.is_file() else shutil.which("jobtracker-bg")


def start_menu_path() -> Path:
    appdata = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Job Tracker.url"


def _start_windows(s: Settings) -> list[str]:
    bg = _bg_exe()
    if not bg:
        return ["Couldn't find jobtracker-bg.exe. Install with `uv tool install .` first, then run this again."]
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([bg, "serve"], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return [f"Running in the background: http://localhost:{s.port}  (log: {log_path()})"]


def _stop_windows() -> None:
    subprocess.run(["taskkill", "/IM", "jobtracker-bg.exe", "/F"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _install_windows(s: Settings, start: bool) -> list[str]:
    bg = _bg_exe()
    if not bg:
        return ["Couldn't find jobtracker-bg.exe. Install with `uv tool install .` first, then run this again."]
    reg = _winreg()
    with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as k:
        reg.SetValueEx(k, RUN_VALUE, 0, reg.REG_SZ, f'"{bg}" serve')
    link = start_menu_path()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.write_text(f"[InternetShortcut]\nURL=http://localhost:{s.port}/\n", "utf-8")
    msgs = [f"Start menu: {link}", "Starts when you sign in to Windows."]
    if start:
        _stop_windows()  # replace a copy that's already running
        msgs += _start_windows(s)
    return msgs


def _uninstall_windows() -> list[str]:
    _stop_windows()
    reg = _winreg()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as k:
            reg.DeleteValue(k, RUN_VALUE)
    except FileNotFoundError:
        pass
    start_menu_path().unlink(missing_ok=True)
    return ["Stopped it and removed it from sign-in and the Start menu.",
            f"Kept your settings ({config_dir() / 'env'}) and your database."]
