"""Sample data for the public demo (JOBTRACKER_DEMO=1).

Every company here is invented. Dates are relative to today, so the demo always
looks current: some follow-ups are due, some deadlines are coming up.
"""

from __future__ import annotations

import datetime as dt
import uuid

import psycopg
from psycopg.types.json import Jsonb

from . import db
from .models import ApplicationIn

RESUME_ML = "Resume – ML v3"
RESUME_SWE = "Resume – SWE v5"
RESUME_DATA = "Resume – Data v2"

# company, role, type, sector, location, mode, salary, source, resume,
# path: [(stage, days_ago), ...] oldest first (first entry is the application date unless wishlist),
# extras: dict of optional fields (nextStep, followUp, deadline, referral, contact, notes, extra notes events)
SAMPLES: list[tuple] = [
    # ---- wishlist
    ("Orchard AI", "Machine Learning Engineer, New Grad", "Full-time", "Tech", "New York, NY", "Hybrid",
     "$135k–$155k", "LinkedIn", "", [("wishlist", 3)],
     {"deadline": -9, "nextStep": "Tailor resume to the ranking/recsys bullets", "notes": "Team works on search ranking. Ask Priya about the interview loop."}),
    ("Saltmarsh Games", "Backend Engineer Intern (Summer 2027)", "Internship", "Tech", "Remote", "Remote",
     "$42/hr", "Handshake", "", [("wishlist", 6)], {"deadline": -4}),
    ("Juniper Transit Authority", "Data Analyst I", "Full-time", "Government", "Newark, NJ", "On-site",
     "$78k–$92k", "Company site", "", [("wishlist", 2)], {"deadline": -15}),
    ("Basalt Data", "Data Engineer, Early Career", "Full-time", "Tech", "Jersey City, NJ", "Hybrid",
     "", "Harper", "", [("wishlist", 1)], {"notes": "Recommended by Harper. dbt + Airflow + Snowflake stack."}),
    ("Fennel & Co.", "Technology Consulting Analyst", "Full-time", "Consulting", "New York, NY", "Hybrid",
     "$95k", "Career fair", "", [("wishlist", 10)], {"contact": "Dana Whitfield (campus recruiting)"}),

    # ---- applied
    ("Larkspur Capital", "Quant Developer Intern", "Internship", "Finance", "New York, NY", "On-site",
     "$65/hr", "Company site", RESUME_SWE, [("applied", 12)],
     {"followUp": -1, "nextStep": "Follow up with recruiter if no word by Friday"}),
    ("Northwind Analytics", "Software Engineer I", "Full-time", "Tech", "Boston, MA", "Hybrid",
     "$120k–$140k", "LinkedIn", RESUME_SWE, [("applied", 5)], {}),
    ("Copperline Bank", "Data Engineering Analyst", "Full-time", "Finance", "Charlotte, NC", "Hybrid",
     "$98k", "Indeed", RESUME_DATA, [("applied", 19)], {"followUp": 2}),
    ("Tidewater Labs", "AI Research Engineer Intern", "Internship", "Tech", "Remote", "Remote",
     "$55/hr", "Referral", RESUME_ML, [("applied", 8)],
     {"referral": "Marcus Lee (Stevens alum)", "nextStep": "Thank Marcus for the referral"}),
    ("Brightwater Insurance", "Machine Learning Intern", "Internship", "Finance", "Hartford, CT", "Hybrid",
     "$38/hr", "Handshake", RESUME_ML, [("applied", 26)], {"followUp": -6}),
    ("Quillon Systems", "Full-Stack Engineer, New Grad", "Full-time", "Tech", "Austin, TX", "On-site",
     "$118k", "Company site", RESUME_SWE, [("applied", 3)], {}),
    ("Kestrel Defense", "Software Engineer, Autonomy", "Full-time", "Defense", "Arlington, VA", "On-site",
     "$110k–$130k", "LinkedIn", RESUME_SWE, [("applied", 15)], {"notes": "Requires U.S. person status."}),
    ("Vantage Point Partners", "Data Science Analyst", "Full-time", "Consulting", "Philadelphia, PA", "Hybrid",
     "$90k", "Recruiter", RESUME_DATA, [("applied", 9)], {"contact": "Sam Ortiz (recruiter)"}),
    ("Cinder Security", "Detection Engineer Intern", "Internship", "Tech", "Remote", "Remote",
     "$45/hr", "LinkedIn", RESUME_SWE, [("applied", 1)], {}),

    # ---- assessment
    ("Halcyon Robotics", "Perception Software Intern", "Internship", "Tech", "Pittsburgh, PA", "On-site",
     "$50/hr", "Company site", RESUME_ML, [("applied", 18), ("assessment", 6)],
     {"nextStep": "Finish the CodeSignal assessment", "followUp": -2}),
    ("Meridian Grid", "Platform Engineer, New Grad", "Full-time", "Tech", "Remote", "Remote",
     "$125k", "Harper", RESUME_SWE, [("applied", 22), ("assessment", 11)], {"notes": "Take-home: build a rate limiter."}),
    ("Copperline Bank", "Technology Analyst Program", "Full-time", "Finance", "New York, NY", "Hybrid",
     "$105k", "Career fair", RESUME_SWE, [("applied", 30), ("assessment", 20)],
     {"nextStep": "HireVue video interview due Sunday", "followUp": 1}),

    # ---- interview
    ("Bramble Health", "ML Engineer Intern", "Internship", "Tech", "New York, NY", "Hybrid",
     "$48/hr", "Referral", RESUME_ML, [("applied", 34), ("assessment", 25), ("interview", 10)],
     {"referral": "Jenna Park", "nextStep": "Final round Thursday — review model evaluation & SQL",
      "followUp": 0, "contact": "Ali Rahman (hiring manager)",
      "events": [(4, "Round 2 with Ali went well — asked about class imbalance")]}),
    ("Northwind Analytics", "Data Engineer Intern", "Internship", "Tech", "Boston, MA", "Hybrid",
     "$44/hr", "Handshake", RESUME_DATA, [("applied", 40), ("interview", 14)],
     {"nextStep": "Send thank-you note to the panel", "followUp": -3}),
    ("Larkspur Capital", "Software Engineer, Trading Systems", "Full-time", "Finance", "New York, NY", "On-site",
     "$160k + bonus", "Recruiter", RESUME_SWE, [("applied", 28), ("assessment", 21), ("interview", 7)],
     {"nextStep": "Superday on the 2nd — practice order-book design"}),
    ("Kestrel Defense", "Data Scientist I", "Full-time", "Defense", "Huntsville, AL", "On-site",
     "$105k", "Company site", RESUME_ML, [("applied", 45), ("interview", 20)], {}),

    # ---- offer
    ("Tidewater Labs", "Software Engineer Intern", "Internship", "Tech", "Hoboken, NJ", "Hybrid",
     "$52/hr", "Career fair", RESUME_SWE, [("applied", 60), ("assessment", 52), ("interview", 38), ("offer", 9)],
     {"deadline": -12, "nextStep": "Decide by the deadline — ask about return-offer rate",
      "events": [(8, "Offer call with recruiter; housing stipend included")]}),

    # ---- closed
    ("Orchard AI", "Applied Scientist Intern", "Internship", "Tech", "New York, NY", "Hybrid",
     "", "LinkedIn", RESUME_ML, [("applied", 50), ("assessment", 41), ("rejected", 33)], {}),
    ("Quillon Systems", "Backend Engineer Intern", "Internship", "Tech", "Austin, TX", "On-site",
     "", "Handshake", RESUME_SWE, [("applied", 55), ("rejected", 47)], {}),
    ("Meridian Grid", "Data Analyst Intern", "Internship", "Tech", "Remote", "Remote",
     "", "Indeed", RESUME_DATA, [("applied", 48), ("interview", 35), ("rejected", 27)],
     {"notes": "Feedback: strong SQL, wanted more dashboarding experience."}),
    ("Brightwater Insurance", "Actuarial Data Intern", "Internship", "Finance", "Hartford, CT", "On-site",
     "", "Handshake", RESUME_DATA, [("applied", 70), ("rejected", 52)], {}),
    ("Vantage Point Partners", "Business Technology Analyst", "Full-time", "Consulting", "New York, NY", "Hybrid",
     "", "Company site", RESUME_SWE, [("applied", 66), ("assessment", 58), ("rejected", 44)], {}),
    ("Saltmarsh Games", "Gameplay Engineer, New Grad", "Full-time", "Tech", "Seattle, WA", "On-site",
     "", "LinkedIn", RESUME_SWE, [("applied", 95), ("ghosted", 30)], {}),
    ("Cinder Security", "Security Engineer I", "Full-time", "Tech", "Remote", "Remote",
     "", "Indeed", RESUME_SWE, [("applied", 88), ("ghosted", 25)], {}),
    ("Fennel & Co.", "Summer Analyst", "Internship", "Consulting", "Boston, MA", "On-site",
     "", "Career fair", RESUME_DATA, [("applied", 58), ("interview", 45), ("withdrawn", 39)],
     {"notes": "Withdrew — role turned out to be mostly slide decks."}),
]

STAGE_TEXT = {
    "wishlist": "Saved", "applied": "Applied", "assessment": "Assessment received",
    "interview": "Interview scheduled", "offer": "Offer received", "rejected": "Rejected",
    "ghosted": "Marked ghosted", "withdrawn": "Withdrew application",
}

# Pending Gmail suggestions shown in the "From Gmail" panel: (company, role, proposed stage, days ago, subject, snippet)
SUGGESTIONS = [
    ("Halcyon Robotics", "Perception Software Intern", "interview", 0,
     "Next steps: interview with Halcyon Robotics",
     "Thanks for completing the assessment! We'd like to invite you to a 45-minute technical interview…"),
    ("Copperline Bank", "Data Engineering Analyst", "rejected", 1,
     "Your application to Copperline Bank",
     "Thank you for your interest. After careful review, we have decided to move forward with other candidates…"),
]


def _app(sample: tuple, today: dt.date) -> tuple[uuid.UUID, ApplicationIn]:
    company, role, typ, sector, loc, mode, salary, source, resume, path, extra = sample
    day = lambda n: today - dt.timedelta(days=n)  # noqa: E731
    events = []
    for stage, ago in path:
        if stage != "wishlist":
            events.append({"date": day(ago), "kind": "stage", "stage": stage, "text": STAGE_TEXT[stage]})
    for ago, text in extra.get("events", []):
        events.append({"date": day(ago), "kind": "note", "text": text})
    events.sort(key=lambda e: e["date"])
    applied = next((day(a) for s, a in path if s == "applied"), None)
    data = ApplicationIn(
        company=company, role=role, stage=path[-1][0], type=typ, sector=sector, location=loc, mode=mode,
        salary=salary, source=source, resume=resume, appliedDate=applied,
        deadline=day(extra["deadline"]) if "deadline" in extra else None,
        followUp=day(extra["followUp"]) if "followUp" in extra else None,
        nextStep=extra.get("nextStep", ""), referral=extra.get("referral", ""),
        contact=extra.get("contact", ""), notes=extra.get("notes", ""),
        url=f"https://careers.example.com/{company.lower().replace(' ', '-').replace('&', 'and').replace('.', '')}",
        events=events,
        createdAt=int(dt.datetime.combine(day(path[0][1]), dt.time(12), dt.timezone.utc).timestamp() * 1000),
    )
    # Stable ids so links to a card keep working across resets.
    return uuid.uuid5(uuid.NAMESPACE_URL, f"jobtracker-demo/{company}/{role}"), data


def reset(conn: psycopg.Connection, today: dt.date | None = None) -> int:
    """Wipe everything and load the sample data. Returns the number of applications."""
    today = today or dt.date.today()
    ids: dict[tuple[str, str], uuid.UUID] = {}
    with conn.transaction():
        conn.execute("TRUNCATE gmail_suggestions, gmail_messages, application_events, applications "
                     "RESTART IDENTITY CASCADE")
        for sample in SAMPLES:
            app_id, data = _app(sample, today)
            db.upsert_application(conn, app_id, data)
            ids[(data.company, data.role)] = app_id
        for n, (company, role, stage, ago, subject, snippet) in enumerate(SUGGESTIONS):
            msgid = f"demo-{n}"
            when = dt.datetime.combine(today - dt.timedelta(days=ago), dt.time(9, 30)).astimezone()
            conn.execute(
                """INSERT INTO gmail_messages (gm_msgid, received_at, sender, subject, kind, outcome, application_id)
                   VALUES (%s, %s, %s, %s, %s, 'suggested', %s)""",
                (msgid, when, f"{company} Recruiting <jobs@example.com>", subject, stage, ids[(company, role)]))
            conn.execute(
                """INSERT INTO gmail_suggestions (gm_msgid, application_id, proposed_stage, occurred_on, subject, snippet, gmail_url)
                   VALUES (%s, %s, %s, %s, %s, %s, '')""",
                (msgid, ids[(company, role)], stage, when.date(), subject, snippet))
        conn.execute(
            """INSERT INTO gmail_sync_state (id, last_sync_at, last_result) VALUES (1, now() - interval '2 hours', %s)
               ON CONFLICT (id) DO UPDATE SET last_sync_at = EXCLUDED.last_sync_at, last_result = EXCLUDED.last_result""",
            (Jsonb({"demo": True}),))
    return len(SAMPLES)


def fake_sync_result(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    return {"scanned": 0, "created": [], "suggested": [], "noted": [],
            "since": (today - dt.timedelta(days=3)).isoformat(), "demo": True}
