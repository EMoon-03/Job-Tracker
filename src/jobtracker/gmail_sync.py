"""Read job emails from Gmail over IMAP (app password) and fold them into the tracker.

New applications are added automatically. Stage changes on applications you already
track (assessment, interview, offer, rejection) become suggestions you accept or dismiss.
Mail is opened read-only and never marked as read.
"""

from __future__ import annotations

import datetime as dt
import email
import email.policy
import email.utils
import html
import imaplib
import re
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from . import db, extract, harper
from .classify import STAGE_RANK, Classified, classify, role_similarity, same_company
from .config import Settings
from .models import ApplicationIn

SYNC_LOCK_ID = 74_220_902

SEARCH_TERMS = (
    'subject:application OR subject:applying OR subject:applied OR subject:interview OR subject:assessment '
    'OR "thank you for applying" OR "thanks for applying" OR "your application" OR "received your application" '
    'OR codesignal OR hackerrank OR codility OR hirevue OR "online assessment" OR "coding assessment" '
    'OR "not to move forward" OR "regret to inform" OR "other candidates" OR "offer letter"'
)
# Harper digests often land in the Promotions tab, so they're searched for separately.
HARPER_SENDER = "from:matchharper.com"


def search_query(since: dt.date) -> str:
    return (f"after:{since:%Y/%m/%d} -in:sent -in:chats "
            f"((-category:promotions ({SEARCH_TERMS})) OR {HARPER_SENDER})")



class GmailError(RuntimeError):
    """A problem the user can fix (bad credentials, IMAP off, …)."""


@dataclass
class Mail:
    gm_msgid: str
    thread_id: str
    received_at: dt.datetime
    sender_name: str
    sender_addr: str
    subject: str
    body: str
    account: str = ""

    @property
    def day(self) -> dt.date:
        return self.received_at.astimezone().date()

    @property
    def snippet(self) -> str:
        return re.sub(r"\s+", " ", self.body).strip()[:280]

    @property
    def gmail_url(self) -> str:
        auth = f"?authuser={self.account}" if self.account else ""
        return f"https://mail.google.com/mail/{auth}#all/thread-f:{self.thread_id}" if self.thread_id else ""


@dataclass
class SyncResult:
    scanned: int = 0
    created: list[str] = field(default_factory=list)
    suggested: list[str] = field(default_factory=list)
    noted: list[str] = field(default_factory=list)
    skipped: int = 0

    def as_dict(self) -> dict:
        return {"scanned": self.scanned, "created": self.created, "suggested": self.suggested,
                "noted": self.noted, "skipped": self.skipped}


# ------------------------------------------------------------------ IMAP

def html_to_text(h: str) -> str:
    h = re.sub(r"(?is)<(style|script|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", h)
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = t.replace("‌", " ").replace("\xa0", " ").replace("͏", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def parse_message(raw: bytes, gm_msgid: str, thread_id: str, account: str = "") -> Mail:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    name, addr = email.utils.parseaddr(str(msg.get("From", "")))
    try:
        received = email.utils.parsedate_to_datetime(str(msg.get("Date")))
        if received.tzinfo is None:
            received = received.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        received = dt.datetime.now(dt.timezone.utc)
    plain = html_body = ""
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        try:
            content = part.get_content()
        except (LookupError, ValueError):
            continue
        if ctype == "text/plain" and not plain:
            plain = str(content)
        elif ctype == "text/html" and not html_body:
            html_body = str(content)
    body = plain
    if len(plain.strip()) < 300 and html_body:  # e.g. Indeed's plain part says almost nothing
        body = (plain + "\n" + html_to_text(html_body)).strip()
    return Mail(gm_msgid=gm_msgid, thread_id=thread_id, received_at=received, sender_name=name,
                sender_addr=addr.lower(), subject=str(msg.get("Subject", "")).strip(), body=body[:20000],
                account=account)


def _all_mail_box(imap: imaplib.IMAP4) -> str:
    typ, boxes = imap.list()
    for line in boxes or []:
        s = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        if "\\All" in s:
            m = re.search(r'"([^"]+)"\s*$', s) or re.search(r"(\S+)\s*$", s)
            if m:
                return m.group(1)
    return "INBOX"


def _imap_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch_mail(settings: Settings, since: dt.date, known: set[str], limit: int = 400) -> list[Mail]:
    if not (settings.gmail_address and settings.gmail_app_password):
        raise GmailError("Gmail isn't set up. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to your .env.")
    try:
        imap = imaplib.IMAP4_SSL(settings.gmail_imap_host, 993, timeout=30)
    except OSError as e:
        raise GmailError(f"Couldn't reach {settings.gmail_imap_host}: {e}") from e
    try:
        try:
            imap.login(settings.gmail_address, settings.gmail_app_password.replace(" ", ""))
        except imaplib.IMAP4.error as e:
            raise GmailError("Gmail rejected the login. Check GMAIL_ADDRESS, and that GMAIL_APP_PASSWORD is a "
                             "16-character app password (not your normal Google password).") from e
        box = _all_mail_box(imap)
        typ, _ = imap.select(_imap_quote(box), readonly=True)
        if typ != "OK":
            raise GmailError(f"Couldn't open the {box} folder.")
        query = search_query(since)
        typ, data = imap.uid("SEARCH", "X-GM-RAW", _imap_quote(query))
        if typ != "OK":
            raise GmailError("Gmail search failed.")
        uids = (data[0] or b"").split()[-limit:]
        if not uids:
            return []
        # First pass: Gmail message ids only, so already-processed mail isn't downloaded again.
        new_uids: list[bytes] = []
        for i in range(0, len(uids), 200):
            typ, resp = imap.uid("FETCH", b",".join(uids[i:i + 200]).decode(), "(X-GM-MSGID)")
            for item in resp or []:
                line = item.decode() if isinstance(item, bytes) else ""
                m_id, m_uid = re.search(r"X-GM-MSGID (\d+)", line), re.search(r"UID (\d+)", line)
                if m_id and m_uid and m_id.group(1) not in known:
                    new_uids.append(m_uid.group(1).encode())
        mails: list[Mail] = []
        for i in range(0, len(new_uids), 25):
            typ, resp = imap.uid("FETCH", b",".join(new_uids[i:i + 25]).decode(), "(X-GM-MSGID X-GM-THRID BODY.PEEK[])")
            for item in resp or []:
                if not isinstance(item, tuple):
                    continue
                head = item[0].decode(errors="replace")
                m_id, m_th = re.search(r"X-GM-MSGID (\d+)", head), re.search(r"X-GM-THRID (\d+)", head)
                if m_id:
                    mails.append(parse_message(item[1], m_id.group(1), m_th.group(1) if m_th else "",
                                               settings.gmail_address))
        return mails
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ------------------------------------------------------------------ processing

def _source_for(mail: Mail) -> str:
    a = mail.sender_addr
    if "linkedin.com" in a:
        return "LinkedIn"
    if "indeed.com" in a:
        return "Indeed"
    if "handshake" in a:
        return "Handshake"
    return ""


def _reached(app: dict) -> set[str]:
    s = {app["stage"]}
    for e in app.get("events", []):
        if e.get("kind") == "stage" and e.get("stage"):
            s.add(e["stage"])
    return s


def find_match(apps: list[dict], company: str, role: str) -> dict | None:
    cands = [a for a in apps if same_company(a["company"], company)]
    if not cands:
        return None
    if len(cands) == 1:
        a = cands[0]
        if role and a.get("role") and role_similarity(role, a["role"]) < 0.15 and len(role.split()) >= 2:
            return None  # same company, clearly a different role
        return a
    if role:
        best = max(cands, key=lambda a: role_similarity(role, a.get("role", "")))
        if role_similarity(role, best.get("role", "")) >= 0.25:
            return best
        return None
    open_ = [a for a in cands if a["stage"] not in ("rejected", "withdrawn", "ghosted")] or cands
    return max(open_, key=lambda a: a.get("updatedAt", 0))


def _save_app(conn: psycopg.Connection, app_id, data: dict) -> dict:
    db.upsert_application(conn, UUID(str(app_id)), ApplicationIn(**data))
    return db.get_application(conn, UUID(str(app_id)))


def _record(conn, mail: Mail, kind: str, outcome: str, app_id=None):
    conn.execute(
        """INSERT INTO gmail_messages (gm_msgid, received_at, sender, subject, kind, outcome, application_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (gm_msgid) DO NOTHING""",
        (mail.gm_msgid, mail.received_at, f"{mail.sender_name} <{mail.sender_addr}>"[:300], mail.subject[:500],
         kind, outcome, app_id),
    )


def known_ids(conn: psycopg.Connection) -> set[str]:
    return {r["gm_msgid"] for r in conn.execute("SELECT gm_msgid FROM gmail_messages")}


def process(conn: psycopg.Connection, mails: list[Mail], settings: Settings) -> SyncResult:
    """Apply a batch of fetched emails. Runs in one transaction."""
    res = SyncResult(scanned=len(mails))
    use_ai = extract.is_available(settings)
    me = (settings.gmail_address or "").lower()
    with conn.transaction():
        apps = db.list_applications(conn)
        done = known_ids(conn)
        for mail in sorted(mails, key=lambda m: m.received_at):
            if mail.gm_msgid in done:
                continue
            done.add(mail.gm_msgid)
            if me and mail.sender_addr == me:
                _record(conn, mail, "other", "skipped"); res.skipped += 1
                continue
            if harper.HARPER_DOMAIN in mail.sender_addr:
                added = 0
                for role in harper.parse(mail.body):
                    if harper.already_tracked(apps, role):
                        continue
                    new_id = str(uuid4())
                    apps.append(_save_app(conn, new_id, harper.to_application(role, mail.day.isoformat())))
                    res.created.append(f"{role.company} – {role.role} (wishlist, from Harper)")
                    added += 1
                _record(conn, mail, "harper", "created" if added else "skipped")
                if not added:
                    res.skipped += 1
                continue
            c: Classified = classify(mail.subject, mail.body, mail.sender_name, mail.sender_addr)
            if c.kind != "other" and not c.company and use_ai:
                try:
                    guess = extract.classify_email(mail.subject, mail.body, settings)
                    c = Classified(kind=c.kind, company=guess.get("company", ""), role=c.role or guess.get("role", ""), stage=c.stage)
                except Exception:
                    pass
            if c.kind == "other" or not c.company:
                _record(conn, mail, c.kind, "skipped"); res.skipped += 1
                continue

            day = mail.day.isoformat()
            match = find_match(apps, c.company, c.role)
            who = match or {"company": c.company, "role": c.role}
            label = who["company"] + (f" – {who.get('role')}" if who.get("role") else "")

            if c.kind in ("viewed", "assessment_done"):
                if not match:
                    _record(conn, mail, c.kind, "skipped"); res.skipped += 1
                    continue
                text = "Application viewed" if c.kind == "viewed" else "Completed the assessment"
                if any(e.get("date") == day and e.get("text") == text for e in match.get("events", [])):
                    _record(conn, mail, c.kind, "skipped", match["id"]); res.skipped += 1
                    continue
                match["events"] = match.get("events", []) + [{"date": day, "kind": "note", "stage": "", "text": text}]
                saved = _save_app(conn, match["id"], match)
                apps[apps.index(match)] = saved
                _record(conn, mail, c.kind, "noted", match["id"]); res.noted.append(f"{label}: {text.lower()}")
                continue

            if match is None:
                # Something we don't track yet: add it, at the stage this email implies.
                stage = c.stage or "applied"
                events = []
                if stage != "rejected" or c.kind == "applied":
                    events.append({"date": day, "kind": "stage", "stage": "applied", "text": ""})
                if stage != "applied":
                    events.append({"date": day, "kind": "stage", "stage": stage, "text": ""})
                new_id = str(uuid4())
                data = {"company": c.company, "role": c.role, "stage": stage, "source": _source_for(mail),
                        "appliedDate": day if stage != "rejected" else "", "events": events,
                        "notes": f"Added from Gmail: “{mail.subject[:160]}”"}
                saved = _save_app(conn, new_id, data)
                apps.append(saved)
                _record(conn, mail, c.kind, "created", new_id)
                res.created.append(f"{label} ({stage})")
                continue

            # Tracked already: suggest the stage change unless it's already happened.
            reached = _reached(match)
            proposed = c.stage
            already = proposed in reached or (
                proposed in STAGE_RANK and match["stage"] in STAGE_RANK and STAGE_RANK[match["stage"]] >= STAGE_RANK[proposed])
            if not proposed or already or (match["stage"] in ("rejected", "withdrawn", "ghosted") and proposed != "offer"):
                _record(conn, mail, c.kind, "skipped", match["id"]); res.skipped += 1
                continue
            _record(conn, mail, c.kind, "suggested", match["id"])
            conn.execute(
                """INSERT INTO gmail_suggestions (gm_msgid, application_id, proposed_stage, occurred_on, subject, snippet, gmail_url)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (mail.gm_msgid, match["id"], proposed, day, mail.subject[:500], mail.snippet, mail.gmail_url),
            )
            res.suggested.append(f"{label} → {proposed}")
    return res


def sync(conn: psycopg.Connection, settings: Settings, since: dt.date | None = None) -> dict:
    got = conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (SYNC_LOCK_ID,)).fetchone()
    if not got["ok"]:
        raise GmailError("A Gmail sync is already running.")
    try:
        if since is None:
            row = conn.execute("SELECT last_sync_at FROM gmail_sync_state WHERE id = 1").fetchone()
            if settings.gmail_since and not (row and row["last_sync_at"]):
                since = settings.gmail_since
            elif row and row["last_sync_at"]:
                since = row["last_sync_at"].astimezone().date() - dt.timedelta(days=3)
            else:
                since = dt.date.today() - dt.timedelta(days=30)
        mails = fetch_mail(settings, since, known_ids(conn))
        result = process(conn, mails, settings).as_dict()
        result["since"] = since.isoformat()
        conn.execute(
            """INSERT INTO gmail_sync_state (id, last_sync_at, last_result) VALUES (1, now(), %s)
               ON CONFLICT (id) DO UPDATE SET last_sync_at = EXCLUDED.last_sync_at, last_result = EXCLUDED.last_result""",
            (Jsonb(result),),
        )
        return result
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (SYNC_LOCK_ID,))


# ------------------------------------------------------------------ review

def status(conn: psycopg.Connection, settings: Settings) -> dict:
    row = conn.execute("SELECT last_sync_at, last_result FROM gmail_sync_state WHERE id = 1").fetchone()
    pending = conn.execute("SELECT count(*) AS n FROM gmail_suggestions WHERE status = 'pending'").fetchone()["n"]
    return {"configured": bool(settings.gmail_address and settings.gmail_app_password),
            "address": settings.gmail_address or "",
            "lastSyncAt": row["last_sync_at"].isoformat() if row and row["last_sync_at"] else None,
            "lastResult": row["last_result"] if row else None,
            "pending": pending}


def pending_suggestions(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id, s.application_id, s.proposed_stage, s.occurred_on, s.subject, s.snippet, s.gmail_url,
                  a.company, a.role, a.stage
           FROM gmail_suggestions s JOIN applications a ON a.id = s.application_id
           WHERE s.status = 'pending' ORDER BY s.occurred_on DESC, s.id DESC""").fetchall()
    return [{"id": r["id"], "applicationId": str(r["application_id"]), "proposedStage": r["proposed_stage"],
             "date": r["occurred_on"].isoformat(), "subject": r["subject"], "snippet": r["snippet"],
             "gmailUrl": r["gmail_url"], "company": r["company"], "role": r["role"], "currentStage": r["stage"]}
            for r in rows]


def resolve_suggestion(conn: psycopg.Connection, sid: int, accept: bool) -> dict | None:
    with conn.transaction():
        s = conn.execute("SELECT * FROM gmail_suggestions WHERE id = %s AND status = 'pending' FOR UPDATE", (sid,)).fetchone()
        if not s:
            return None
        app = None
        if accept:
            app = db.get_application(conn, s["application_id"])
            if app:
                day = s["occurred_on"].isoformat()
                app["stage"] = s["proposed_stage"]
                app["events"] = app.get("events", []) + [
                    {"date": day, "kind": "stage", "stage": s["proposed_stage"], "text": f"From Gmail: {s['subject'][:150]}"}]
                if s["proposed_stage"] == "applied" and not app.get("appliedDate"):
                    app["appliedDate"] = day
                if s["proposed_stage"] == "rejected":
                    app["followUp"] = ""
                    app["nextStep"] = ""
                app = _save_app(conn, s["application_id"], app)
        conn.execute("UPDATE gmail_suggestions SET status = %s, resolved_at = now() WHERE id = %s",
                     ("accepted" if accept else "dismissed", sid))
        return app or {"ok": True}
