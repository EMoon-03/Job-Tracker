import datetime as dt
import uuid
from email.message import EmailMessage

import psycopg
import pytest

from conftest import TEST_DB
from jobtracker import gmail_sync
from jobtracker.config import Settings

SETTINGS = Settings(database_url=TEST_DB, anthropic_api_key=None, claude_model="x", host="127.0.0.1", port=0,
                    gmail_address="alex.kim@example.com", gmail_app_password="abcd efgh ijkl mnop")


def mail(mid, subject, body, name, addr, day="2026-11-10"):
    return gmail_sync.Mail(gm_msgid=str(mid), thread_id=str(mid) + "9", sender_name=name, sender_addr=addr,
                           received_at=dt.datetime.fromisoformat(day + "T15:00:00+00:00"), subject=subject, body=body,
                           account=SETTINGS.gmail_address)


def seed(client, company, role, stage="applied", applied="2026-10-01"):
    app_id = str(uuid.uuid4())
    events = [{"date": applied, "kind": "stage", "stage": "applied"}] if stage != "wishlist" else []
    r = client.put(f"/api/applications/{app_id}", json={"company": company, "role": role, "stage": stage,
                                                       "appliedDate": applied if stage != "wishlist" else "", "events": events})
    assert r.status_code == 200
    return app_id


MAILS = [
    mail(1, "Kitewire invited you to take Kitewire 2025 Coding Assessment (Industry Coding Assessment) on CodeSignal",
         "Hey Alex, You've just been invited by someone from Kitewire to take Kitewire 2025 Coding Assessment.", "CodeSignal", "no-reply@codesignal.com"),
    mail(2, "Your application - Software Engineering Intern (Summer) at Lanternfish",
         "Thanks again for your interest in Lanternfish. We have decided not to move forward with your application.",
         "Lanternfish Recruiting", "no-reply@recruiting.lanternfishhq.com", "2026-11-12"),
    mail(3, "Thank you for applying to Brightloom!",
         "Hi Alex, Thank you for your application for the Intern, Software Engineering position! At Brightloom, we're all about",
         "", "no-reply@brightloom.com"),
    mail(4, "Your application was viewed by Wren", "Your application was viewed by Wren", "LinkedIn", "jobs-noreply@linkedin.com"),
    mail(5, "Big Tech Layoffs Hit Quant?", "Bastion built an AI system...", "WallStreetQuants", "info@thewallstreetquants.com"),
    mail(6, "Thank you for applying to Senix Robotics",
         "Thank you for applying to the AI-Native Software Engineer role at Senix Robotics.", "", "careers@senixrobotics.com"),
    mail(7, "Re: Follow-up", "Unfortunately I'm unavailable that day.", "Alex Kim", "alex.kim@example.com"),
    mail(8, "Assessment completed: Kitewire 2025 Coding Assessment",
         "Hi Alex, You have completed the Kitewire 2025 Coding Assessment.", "CodeSignal", "no-reply@codesignal.com", "2026-11-12"),
    mail(9, "Your application to Software Engineer, Quality [SDET] at NovaLedger",
         "Unfortunately, NovaLedger has decided not to move forward with your application.", "LinkedIn", "jobs-noreply@linkedin.com"),
]


@pytest.fixture()
def seeded(client):
    ids = {
        "kitewire": seed(client, "Kitewire", "Software Engineer"),
        "lanternfish": seed(client, "Lanternfish", "Software Engineering Intern (Summer)", applied="2026-09-29"),
        "senix": seed(client, "Senix Robotics", "AI-Native Software Engineer", stage="wishlist"),
    }
    return client, ids


def run(mails):
    with psycopg.connect(TEST_DB, row_factory=psycopg.rows.dict_row, autocommit=True) as conn:
        return gmail_sync.process(conn, mails, SETTINGS)


def test_process_creates_suggests_and_dedupes(seeded):
    client, ids = seeded
    r = run(MAILS)
    assert r.scanned == len(MAILS)
    assert any(c.startswith("Brightloom") for c in r.created)
    assert any(c.startswith("NovaLedger") and "(rejected)" in c for c in r.created)
    assert sorted(s.split(" → ")[1] for s in r.suggested) == ["applied", "assessment", "rejected"]
    assert any("completed the assessment" in n for n in r.noted)
    assert r.skipped == 3  # Wren (not tracked), newsletter, own email

    again = run(MAILS)  # same mail twice → nothing new
    assert (again.created, again.suggested, again.noted) == ([], [], [])

    apps = {a["company"]: a for a in client.get("/api/applications").json()}
    assert apps["Brightloom"]["stage"] == "applied" and apps["Brightloom"]["appliedDate"] == "2026-11-10"
    assert "Intern, Software Engineering" in apps["Brightloom"]["role"]
    assert apps["Kitewire"]["stage"] == "applied"  # suggestions don't change anything yet
    assert any(e["text"] == "Completed the assessment" for e in apps["Kitewire"]["events"])


def test_accept_and_dismiss(seeded):
    client, ids = seeded
    run(MAILS)
    pending = client.get("/api/gmail/suggestions").json()
    by_company = {p["company"]: p for p in pending}
    assert set(by_company) == {"Kitewire", "Lanternfish", "Senix Robotics"}
    assert by_company["Kitewire"]["gmailUrl"].startswith("https://mail.google.com/")

    r = client.post(f"/api/gmail/suggestions/{by_company['Kitewire']['id']}/accept")
    assert r.status_code == 200 and r.json()["stage"] == "assessment"
    assert {"date": "2026-11-10", "kind": "stage", "stage": "assessment"}.items() <= next(
        e for e in r.json()["events"] if e["stage"] == "assessment").items()

    r = client.post(f"/api/gmail/suggestions/{by_company['Senix Robotics']['id']}/accept")
    assert r.json()["stage"] == "applied" and r.json()["appliedDate"] == "2026-11-10"

    assert client.post(f"/api/gmail/suggestions/{by_company['Lanternfish']['id']}/dismiss").status_code == 200
    assert client.get(f"/api/applications/{ids['lanternfish']}").json()["stage"] == "applied"
    assert client.post(f"/api/gmail/suggestions/{by_company['Lanternfish']['id']}/dismiss").status_code == 404
    assert client.get("/api/gmail/suggestions").json() == []


def test_status_without_credentials(client):
    s = client.get("/api/gmail/status").json()
    assert s["configured"] is False and s["pending"] == 0
    r = client.post("/api/gmail/sync")
    assert r.status_code == 400 and "GMAIL_APP_PASSWORD" in r.json()["detail"]


def test_parse_html_only_message():
    m = EmailMessage()
    m["From"] = "Indeed Apply <indeedapply@indeed.com>"
    m["Subject"] = "Indeed Application: Software Engineers"
    m["Date"] = "Wed, 07 Oct 2026 17:36:36 +0000"
    m.set_content("Your application has been submitted. Good luck!")
    m.add_alternative("<html><body><p>Application submitted</p><p>Software Engineers</p><p>ZQT Inc</p>"
                      "<p>The following items were sent to ZQT Inc. Good luck!</p></body></html>", subtype="html")
    parsed = gmail_sync.parse_message(m.as_bytes(), "42", "4242", "me@gmail.com")
    assert "sent to ZQT Inc" in parsed.body
    assert parsed.day == dt.date(2026, 10, 7) or parsed.day == dt.date(2026, 10, 8)
    assert parsed.gmail_url.endswith("#all/thread-f:4242")


class FakeIMAP:
    """Just enough of imaplib.IMAP4_SSL for fetch_mail."""

    def __init__(self, *a, **k):
        msg = EmailMessage()
        msg["From"] = "Brightloom <no-reply@brightloom.com>"
        msg["Subject"] = "Thank you for applying to Brightloom!"
        msg["Date"] = "Tue, 10 Nov 2026 14:24:06 +0000"
        msg.set_content("Thank you for your application for the Intern, Software Engineering position!")
        self.raw = msg.as_bytes()
        self.searched = None

    def login(self, user, pw):
        assert pw == "abcdefghijklmnop"  # spaces stripped
        return "OK", [b"ok"]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"']

    def select(self, box, readonly=False):
        assert box == '"[Gmail]/All Mail"' and readonly
        return "OK", [b"2"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            self.searched = args[-1]
            return "OK", [b"1 2"]
        if args[-1] == "(X-GM-MSGID)":
            return "OK", [b"1 (X-GM-MSGID 111 UID 1)", b"2 (X-GM-MSGID 222 UID 2)"]
        assert args[0] == "2"  # 111 is already known, so only uid 2 is downloaded
        return "OK", [(b"2 (X-GM-MSGID 222 X-GM-THRID 999 UID 2 BODY[] {%d}" % len(self.raw), self.raw), b")"]

    def logout(self):
        return "BYE", []


def test_fetch_mail_with_fake_imap(monkeypatch):
    monkeypatch.setattr(gmail_sync.imaplib, "IMAP4_SSL", FakeIMAP)
    mails = gmail_sync.fetch_mail(SETTINGS, dt.date(2026, 11, 1), known={"111"})
    assert [m.gm_msgid for m in mails] == ["222"]
    assert mails[0].subject == "Thank you for applying to Brightloom!" and mails[0].thread_id == "999"


HARPER_MAIL = mail(50, "Alex, two new AI-focused early-career roles",
    "Hi Alex,\n\nQuora · Machine Learning Engineer, New Grad (https://matchharper.com/career/history?historyTab=new&id=ec86798a-af59-5252-874f-934d5b47d2c4) — Remote US role on LLM agents. Employer posting (https://careers.quora.com/)\n\n"
    "- Lanternfish · Software Engineering Intern (Summer): https://matchharper.com/career/history?historyTab=new&id=993eee29-18f1-582f-9be8-81f55b05cf54 — already tracked\n",
    "Harper", "hello@matchharper.com", "2026-11-14")


def test_harper_digest_adds_wishlist(seeded):
    client, ids = seeded
    r = run([HARPER_MAIL])
    assert r.created == ["Quora – Machine Learning Engineer, New Grad (wishlist, from Harper)"]  # Lanternfish already tracked
    quora = next(a for a in client.get("/api/applications").json() if a["company"] == "Quora")
    assert quora["stage"] == "wishlist" and quora["source"] == "Harper" and quora["url"] == "https://careers.quora.com/"
    assert "ec86798a-af59-5252-874f-934d5b47d2c4" in quora["notes"]
    # a later digest repeating the same role (different email) doesn't duplicate it
    again = run([mail(51, "repeat", HARPER_MAIL.body, "Harper", "hello@matchharper.com", "2026-11-16")])
    assert again.created == []


def test_search_includes_harper_even_in_promotions():
    import datetime as dt
    q = gmail_sync.search_query(dt.date(2026, 11, 1))
    assert q.startswith("after:2026/11/01 -in:sent -in:chats ")
    # Promotions are excluded only for the job-email terms; Harper's sender is matched on its own.
    assert q.endswith(f"OR {gmail_sync.HARPER_SENDER})")
    assert "(-category:promotions (" in q and q.count("(") == q.count(")")
