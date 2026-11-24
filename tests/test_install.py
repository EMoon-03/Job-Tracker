import os

import psycopg
import pytest

from jobtracker import config, install
from jobtracker.config import get_settings

from conftest import TEST_DB


@pytest.fixture
def home(tmp_path, monkeypatch):
    # Loading an env file writes into os.environ; put it back so nothing leaks into later tests.
    saved = dict(os.environ)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / ".local/share"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


def test_settings_come_from_the_config_dir(home, monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    env = config.config_dir() / "env"
    env.parent.mkdir(parents=True)
    env.write_text("GMAIL_ADDRESS=someone@example.com\n")
    assert get_settings().gmail_address == "someone@example.com"


def test_local_env_wins_over_config_dir(home, monkeypatch):
    monkeypatch.delenv("JOBTRACKER_PORT", raising=False)
    (config.config_dir()).mkdir(parents=True)
    (config.config_dir() / "env").write_text("JOBTRACKER_PORT=9000\n")
    (home / "work" / ".env").write_text("JOBTRACKER_PORT=9100\n")
    assert get_settings().port == 9100


def test_install_writes_service_launcher_and_settings(home, monkeypatch):
    monkeypatch.setattr(install, "_exe", lambda: "/home/me/.local/bin/jobtracker")
    (home / "work" / ".env").write_text("GMAIL_ADDRESS=a@b.c\n")
    msgs = install.install(get_settings(), start=False)

    env = config.config_dir() / "env"
    assert env.read_text() == "GMAIL_ADDRESS=a@b.c\n"           # copied from ./.env
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    assert "ExecStart=/home/me/.local/bin/jobtracker serve" in install.unit_path().read_text()
    assert "Exec=xdg-open http://localhost:" in install.desktop_path().read_text()
    assert any("systemctl --user enable --now jobtracker" in m for m in msgs)

    env.write_text("# mine\n")
    install.install(get_settings(), start=False)                 # never overwrites settings
    assert env.read_text() == "# mine\n"

    monkeypatch.setattr(install, "_systemctl", lambda *a: True)
    install.uninstall()
    assert not install.unit_path().exists() and not install.desktop_path().exists()
    assert env.exists()


def test_ensure_database_creates_a_missing_database():
    url = TEST_DB + "_fresh"
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS jobtracker_test_fresh")
    try:
        assert install.ensure_database(url) is True
        assert install.ensure_database(url) is False             # already there
    finally:
        with psycopg.connect(TEST_DB, autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS jobtracker_test_fresh")


# ---- Windows (simulated: a fake registry, recorded subprocess calls)

class FakeWinreg:
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = "HKCU", 2, 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, root, path, reserved, access):  # noqa: N802 - mirrors winreg
        assert (root, path) == ("HKCU", install.RUN_KEY)
        return self._Key()

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        self.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


@pytest.fixture
def windows(home, monkeypatch):
    reg = FakeWinreg()
    calls = []
    bin_dir = home / "bin"
    bin_dir.mkdir()
    (bin_dir / "jobtracker-bg.exe").write_text("")
    monkeypatch.setattr(install, "WINDOWS", True)
    monkeypatch.setattr(install, "_winreg", lambda: reg)
    monkeypatch.setattr(install, "_exe", lambda: str(bin_dir / "jobtracker.exe"))
    monkeypatch.setattr(install.subprocess, "Popen", lambda args, **kw: calls.append(("start", args)))
    monkeypatch.setattr(install.subprocess, "run", lambda args, **kw: calls.append(("run", args)))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    return reg, calls, bin_dir


def test_windows_install_restart_uninstall(windows):
    reg, calls, bin_dir = windows
    bg = str(bin_dir / "jobtracker-bg.exe")
    msgs = install.install(get_settings())

    assert reg.values[install.RUN_VALUE] == f'"{bg}" serve'
    link = install.start_menu_path()
    assert link.name == "Job Tracker.url" and "URL=http://localhost:8765/" in link.read_text()
    assert ("run", ["taskkill", "/IM", "jobtracker-bg.exe", "/F"]) in calls   # replaces a running copy
    assert calls[-1] == ("start", [bg, "serve"])
    assert any("Running in the background" in m for m in msgs)
    assert (config.config_dir() / "env").exists()

    calls.clear()
    install.restart(get_settings())
    assert [c[0] for c in calls] == ["run", "start"]

    install.uninstall()
    assert install.RUN_VALUE not in reg.values and not link.exists()
    install.uninstall()                                          # second time is harmless


def test_windows_install_without_uv_tool_explains(windows, monkeypatch):
    reg, calls, bin_dir = windows
    (bin_dir / "jobtracker-bg.exe").unlink()
    monkeypatch.setattr(install.shutil, "which", lambda name: None)
    msgs = install.install(get_settings())
    assert "uv tool install ." in msgs[-1] and not reg.values and not calls


def test_background_logs_to_a_file(windows, monkeypatch):
    from jobtracker import cli
    seen = []
    monkeypatch.setattr(cli, "main", lambda argv: (seen.append(argv), print("hello from serve")))
    monkeypatch.setattr(cli.sys, "argv", ["jobtracker-bg"])
    monkeypatch.setattr(cli.sys, "stdout", cli.sys.stdout)
    monkeypatch.setattr(cli.sys, "stderr", cli.sys.stderr)
    cli.background()
    assert seen == [["serve"]]
    log = install.log_path()
    assert log.parent.name == "jobtracker" and "Local" in str(log)
    assert "hello from serve" in log.read_text()


def test_config_dir_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.config_dir() == tmp_path / "jobtracker"


def test_backup_finds_pg_dump_in_program_files(monkeypatch, tmp_path):
    from jobtracker import cli
    for v in ("16", "18"):
        d = tmp_path / "PostgreSQL" / v / "bin"
        d.mkdir(parents=True)
        (d / "pg_dump.exe").write_text("")
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert cli._find_pg_dump() == str(tmp_path / "PostgreSQL" / "18" / "bin" / "pg_dump.exe")
