"""`jobtracker` command: run the server, install it as a login service, import, sync, back up."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
import threading
import webbrowser

from .config import get_settings


def main(argv: list[str] | None = None) -> None:
    s = get_settings()
    p = argparse.ArgumentParser(prog="jobtracker", description="Local job application tracker")
    sub = p.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="run the web app (default)")
    serve.add_argument("--host", default=s.host)
    serve.add_argument("--port", type=int, default=s.port)
    serve.add_argument("--open", action="store_true", help="open the tracker in your browser")
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")

    sub.add_parser("migrate", help="create/upgrade the database tables")

    backup = sub.add_parser("backup", help="dump the database to a .sql file with pg_dump")
    backup.add_argument("-o", "--output", help="file to write (default: jobtracker-YYYY-MM-DD.sql)")

    imp = sub.add_parser("import-json", help="import applications (with timelines) from a JSON file")
    imp.add_argument("file", help="a JSON array of applications in the tracker's format")

    gs = sub.add_parser("sync-gmail", help="pull new application emails from Gmail (needs GMAIL_* in .env)")
    gs.add_argument("--since", help="scan mail from this date (YYYY-MM-DD); default: since the last sync")

    inst = sub.add_parser("install", help="run in the background, start on login, add a launcher entry")
    inst.add_argument("--no-start", action="store_true", help="set it up but don't start it now")
    sub.add_parser("restart", help="restart the background app (after editing settings or updating)")
    sub.add_parser("uninstall", help="stop the background app and remove the login entry (keeps settings and data)")

    args = p.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "install":
        from .install import install
        for m in install(s, start=not args.no_start):
            print(m)
        return

    if cmd == "uninstall":
        from .install import uninstall
        for m in uninstall():
            print(m)
        return

    if cmd == "restart":
        from .install import restart
        for m in restart(s):
            print(m)
        return

    if cmd != "backup":
        from .install import ensure_database
        if ensure_database(s.database_url):
            print("Created the database.")

    if cmd == "sync-gmail":
        from . import db, gmail_sync
        since = None
        if args.since:
            try:
                since = dt.date.fromisoformat(args.since)
            except ValueError:
                sys.exit("--since must look like 2026-11-01")
        pool = db.make_pool(s.database_url)
        try:
            with pool.connection() as conn:
                db.migrate(conn)
                r = gmail_sync.sync(conn, s, since=since)
        except gmail_sync.GmailError as e:
            sys.exit(str(e))
        finally:
            pool.close()
        print(f"Scanned {r['scanned']} new emails since {r['since']}.")
        for label, items in (("Added", r["created"]), ("To review in the app", r["suggested"]), ("Noted", r["noted"])):
            if items:
                print(f"{label}:")
                for it in items:
                    print(f"  • {it}")
        if not (r["created"] or r["suggested"] or r["noted"]):
            print("Nothing new.")
        return

    if cmd == "import-json":
        import json
        from pathlib import Path

        from pydantic import TypeAdapter, ValidationError

        from . import db
        from .models import BulkItem
        try:
            items = TypeAdapter(list[BulkItem]).validate_python(json.loads(Path(args.file).read_text("utf-8")))
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            sys.exit(f"Couldn't read {args.file}: {e}")
        pool = db.make_pool(s.database_url)
        with pool.connection() as conn:
            db.migrate(conn)
            result = db.bulk_import(conn, items)
        pool.close()
        print(f"Imported {result['created']} applications; skipped {result['skipped']} already tracked.")
        return

    if cmd == "migrate":
        from . import db
        pool = db.make_pool(s.database_url)
        with pool.connection() as conn:
            done = db.migrate(conn)
        pool.close()
        print("Applied: " + ", ".join(done) if done else "Database is up to date.")
        return

    if cmd == "backup":
        pg_dump = _find_pg_dump()
        if not pg_dump:
            sys.exit("pg_dump not found; install the PostgreSQL client tools.")
        out = args.output or f"jobtracker-{dt.date.today().isoformat()}.sql"
        subprocess.run([pg_dump, "--no-owner", "--file", out, s.database_url], check=True)
        print(f"Wrote {out}")
        return

    import uvicorn

    host = getattr(args, "host", s.host)
    port = getattr(args, "port", s.port)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    print(f"Job Tracker running at {url}  (Ctrl+C to stop)")
    if getattr(args, "open", False):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run("jobtracker.main:app", host=host, port=port,
                reload=getattr(args, "reload", False), log_level="warning")


def _find_pg_dump() -> str | None:
    """pg_dump on PATH, or (Windows) the newest one under Program Files, where the installer puts it."""
    found = shutil.which("pg_dump")
    if found or sys.platform != "win32":
        return found
    import glob
    import os
    root = os.environ.get("ProgramFiles", r"C:\Program Files")
    hits = glob.glob(os.path.join(root, "PostgreSQL", "*", "bin", "pg_dump.exe"))
    return max(hits, key=lambda h: int(h.split(os.sep)[-3]) if h.split(os.sep)[-3].isdigit() else 0) if hits else None


def background() -> None:
    """Entry point for `jobtracker-bg`, which has no console window on Windows: write output to a log file."""
    from .install import log_path
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    out = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the process
    sys.stdout = sys.stderr = out
    print(f"--- started {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    main(sys.argv[1:] or ["serve"])


if __name__ == "__main__":
    main()
