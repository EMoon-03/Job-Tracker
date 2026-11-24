"""FastAPI app: JSON API under /api, the tracker UI at /."""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from contextlib import asynccontextmanager, suppress
from importlib import resources
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import db, demo, extract, gmail_sync
from .config import Settings, get_settings
from .models import ApplicationIn, BulkItem, ExtractIn, GmailSyncIn

log = logging.getLogger("jobtracker")

DEMO_RESET_SECONDS = 60 * 60
DEMO_MAX_APPLICATIONS = 150
MAX_BODY_BYTES = 10_000_000         # local use: big JSON imports are fine
DEMO_MAX_BODY_BYTES = 100_000


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        pool = db.make_pool(settings.database_url)
        with pool.connection() as conn:
            db.migrate(conn)
            if settings.demo_mode:
                demo.reset(conn)
        app.state.pool = pool
        resetter = asyncio.create_task(_reset_demo_forever(pool)) if settings.demo_mode else None
        try:
            yield
        finally:
            if resetter:
                resetter.cancel()
                with suppress(asyncio.CancelledError):
                    await resetter
            pool.close()

    async def _reset_demo_forever(pool):
        while True:
            await asyncio.sleep(DEMO_RESET_SECONDS)
            try:
                await asyncio.to_thread(_reset_once, pool)
            except Exception:  # keep the loop alive; the next tick retries
                log.exception("demo reset failed")

    def _reset_once(pool):
        with pool.connection() as conn:
            demo.reset(conn)

    app = FastAPI(title="Job Tracker", version="0.2.0", lifespan=lifespan,
                  docs_url=None if settings.demo_mode else "/docs", redoc_url=None)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Optional password (HTTP Basic auth) for hosting your own tracker. Health checks stay open.
        if settings.password and request.url.path != "/api/health":
            if not _password_ok(request.headers.get("authorization", ""), settings.password):
                return PlainTextResponse("Password required", status_code=401,
                                         headers={"WWW-Authenticate": 'Basic realm="Job Tracker", charset="UTF-8"'})
        limit = DEMO_MAX_BODY_BYTES if settings.demo_mode else MAX_BODY_BYTES
        try:
            size = int(request.headers.get("content-length") or 0)
        except ValueError:
            size = 0
        if size > limit:
            return JSONResponse({"detail": "Request is too large"}, status_code=413)
        return await call_next(request)

    def no_demo(what: str):
        if settings.demo_mode:
            raise HTTPException(403, f"{what} is turned off in the demo.")

    def conn():
        with app.state.pool.connection() as c:
            yield c

    @app.get("/api/health")
    def health(c=Depends(conn)):
        c.execute("SELECT 1")
        return {"ok": True}

    @app.get("/api/config")
    def config():
        return {"extract": not settings.demo_mode and extract.is_available(settings),
                "ai": None if settings.demo_mode else extract.provider_label(settings),
                "demo": settings.demo_mode, "repoUrl": settings.repo_url,
                "demoResetMinutes": DEMO_RESET_SECONDS // 60 if settings.demo_mode else None}

    @app.get("/api/applications")
    def list_applications(c=Depends(conn)):
        return db.list_applications(c)

    @app.get("/api/applications/{app_id}")
    def get_application(app_id: UUID, c=Depends(conn)):
        app_ = db.get_application(c, app_id)
        if not app_:
            raise HTTPException(404, "Application not found")
        return app_

    @app.put("/api/applications/{app_id}")
    def put_application(app_id: UUID, body: ApplicationIn, c=Depends(conn)):
        if settings.demo_mode and not db.get_application(c, app_id):
            n = c.execute("SELECT count(*) AS n FROM applications").fetchone()["n"]
            if n >= DEMO_MAX_APPLICATIONS:
                raise HTTPException(403, f"The demo holds at most {DEMO_MAX_APPLICATIONS} applications. It resets every hour.")
        return db.save_application(c, app_id, body)

    @app.delete("/api/applications/{app_id}", status_code=204)
    def delete_application(app_id: UUID, c=Depends(conn)):
        db.delete_application(c, app_id)
        return Response(status_code=204)

    @app.post("/api/applications/bulk")
    def bulk(items: list[BulkItem], c=Depends(conn)):
        if len(items) > 5000:
            raise HTTPException(413, "Import at most 5000 rows at a time")
        if settings.demo_mode:
            n = c.execute("SELECT count(*) AS n FROM applications").fetchone()["n"]
            if n + len(items) > DEMO_MAX_APPLICATIONS:
                raise HTTPException(403, f"The demo holds at most {DEMO_MAX_APPLICATIONS} applications. It resets every hour.")
        return db.bulk_import(c, items)

    @app.post("/api/extract")
    def extract_posting(body: ExtractIn):
        no_demo("Filling from a posting")
        try:
            return extract.extract_posting(body.text, settings)
        except extract.ExtractUnavailable as e:
            raise HTTPException(503, str(e)) from e
        except Exception as e:  # network/API/parse problems
            raise HTTPException(502, f"Couldn't read that posting: {e}") from e

    # ---- Gmail sync (IMAP + app password) ----
    @app.get("/api/gmail/status")
    def gmail_status(c=Depends(conn)):
        st = gmail_sync.status(c, settings)
        if settings.demo_mode:  # show the Gmail panel with sample suggestions, never touch real mail
            st.update(configured=True, address="demo@example.com", demo=True)
        return st

    @app.post("/api/gmail/sync")
    def gmail_sync_now(body: GmailSyncIn | None = None, c=Depends(conn)):
        if settings.demo_mode:
            return demo.fake_sync_result()
        try:
            return gmail_sync.sync(c, settings, since=body.since if body else None)
        except gmail_sync.GmailError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/api/gmail/suggestions")
    def gmail_suggestions(c=Depends(conn)):
        return gmail_sync.pending_suggestions(c)

    @app.post("/api/gmail/suggestions/{sid}/{action}")
    def gmail_resolve(sid: int, action: str, c=Depends(conn)):
        if action not in ("accept", "dismiss"):
            raise HTTPException(404, "Unknown action")
        out = gmail_sync.resolve_suggestion(c, sid, accept=action == "accept")
        if out is None:
            raise HTTPException(404, "That suggestion was already handled")
        return out

    static_dir = resources.files("jobtracker") / "static"
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app


def _password_ok(header: str, password: str) -> bool:
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        return False
    try:
        _user, _, given = base64.b64decode(value).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(given.encode(), password.encode())


app = create_app()
