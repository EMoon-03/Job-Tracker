"""Harper digest parsing, using the three formats Harper has actually sent (bodies shortened)."""

from jobtracker import harper

DOT_FORMAT = """Hi Alex,

I found two new full-time roles that lean toward the applied AI and data work you prefer. I added both to your New opportunities list.

Quora · Machine Learning Engineer, New Grad (https://matchharper.com/career/history?historyTab=new&id=ec86798a-af59-5252-874f-934d5b47d2c4) — This remote US role works on LLM-powered agents and ML workflows for content quality and safety. Employer posting (https://careers.quora.com/)

Herald · Software Engineer, AI Products (https://matchharper.com/career/history?historyTab=new&id=baae5204-5ab6-5656-a5b4-3823bdb9dba9) — This is an NYC-based AI startup automating commercial insurance broker workflows.

Both are public postings, so you'd apply directly through the employers. Your other recommendations remain available in Career: see your opportunities (https://matchharper.com/career/history?historyTab=new&entryPoint=delivery_email_history_link).
"""

LIST_FORMAT = """Your recent saves point toward applied ML internships. 18 roles are saved to your Positions tab.

- Kitewire · Applied Scientist Intern: https://matchharper.com/career/history?historyTab=new&id=a6ce484e-0ad2-5acb-a656-48695a932aa7 — A strong NYC-area fintech match, listed as remote.
- Upstart · Applied Scientist Intern: https://matchharper.com/career/history?historyTab=new&id=d8ffb6ee-15ef-5dfb-a06f-3b9c1e9d2539
- rippling · Machine Learning Software Engineer Intern - Winter 2027: https://matchharper.com/career/history?historyTab=new&id=41ce86df-d069-586c-91c7-f77d69795f06

View all opportunities: https://matchharper.com/career/history?historyTab=new
"""

PROSE_FORMAT = """Hi Alex,

I kept full-time opportunities in focus and included one internship as a parallel path. On the full-time side, Applied AI Engineer at Kitewire: https://matchharper.com/career/history?historyTab=new&id=1e30fd26-6b9d-5242-8ced-9e4d91955d86 centers on agents and retrieval-augmented generation; it is listed as remote for New York City. Software Engineer — Product at Snorkel AI: https://matchharper.com/career/history?historyTab=new&id=ecfa9d77-1988-5a20-a653-6ba6450d9b62 offers a more end-to-end product focus.

For the internship route, Software Engineering Intern (Summer) at Lanternfish: https://matchharper.com/career/history?historyTab=new&id=993eee29-18f1-582f-9be8-81f55b05cf54 offers work across production engineering areas.

For two different directions, 2027 Internship Software Engineer, Fleet Platform at Bedrock Robotics: https://matchharper.com/career/history?historyTab=new&id=2ea70895-7fb8-5367-acb6-51c884c0c796 is a summer 2027 opportunity, while Software Engineer I/II - Scientific Computing at Iambic: https://matchharper.com/career/history?historyTab=new&id=1385a11d-8967-5848-afa8-91dfac86cd8d focuses on Python tools.

One more: Software Engineer, (Internal Audit) \\[All Levels\\] at Fieldguide: https://matchharper.com/career/history?historyTab=new&id=c240ae50-c610-598b-93e8-e4b4a937b46c offers a different applied-AI angle.

See all recommendations: https://matchharper.com/career/history?historyTab=new&entryPoint=delivery_email_history_link
"""


def pairs(body):
    return [(r.company, r.role) for r in harper.parse(body)]


def test_dot_format():
    roles = harper.parse(DOT_FORMAT)
    assert pairs(DOT_FORMAT) == [("Quora", "Machine Learning Engineer, New Grad"), ("Herald", "Software Engineer, AI Products")]
    assert roles[0].employer_url == "https://careers.quora.com/"
    assert roles[0].summary.startswith("This remote US role") and "Employer posting" not in roles[0].summary
    assert roles[1].employer_url == ""


def test_list_format():
    assert pairs(LIST_FORMAT) == [("Kitewire", "Applied Scientist Intern"), ("Upstart", "Applied Scientist Intern"),
                                  ("Rippling", "Machine Learning Software Engineer Intern - Winter 2027")]
    assert harper.parse(LIST_FORMAT)[0].is_internship


def test_prose_format():
    got = pairs(PROSE_FORMAT)
    assert got == [
        ("Kitewire", "Applied AI Engineer"),
        ("Snorkel AI", "Software Engineer — Product"),
        ("Lanternfish", "Software Engineering Intern (Summer)"),
        ("Bedrock Robotics", "2027 Internship Software Engineer, Fleet Platform"),
        ("Iambic", "Software Engineer I/II - Scientific Computing"),
        ("Fieldguide", "Software Engineer, (Internal Audit) [All Levels]"),
    ]
    kitewire = harper.parse(PROSE_FORMAT)[0]
    assert "Snorkel" not in kitewire.summary and kitewire.summary.startswith("centers on agents")


def test_already_tracked():
    apps = [{"company": "Lanternfish", "role": "Software Engineering Intern (Summer)", "notes": ""},
            {"company": "Quora", "role": "Software Engineer New Grad, Machine Learning Platform", "notes": ""},
            {"company": "Tessera Labs", "role": "Full Stack Engineer, Intern", "notes": ""},
            {"company": "Adobe", "role": "2027 Intern – Machine Learning Engineer (R171519)", "notes": ""},
            {"company": "Herald", "role": "x", "notes": "Harper: https://matchharper.com/career/history?id=baae5204-5ab6-5656-a5b4-3823bdb9dba9"}]
    R = lambda c, r, i="00000000-0000-0000-0000-000000000000": harper.HarperRole(c, r, i, "", "", "")
    assert harper.already_tracked(apps, R("Lanternfish", "Software Engineering Intern (Summer)"))
    assert harper.already_tracked(apps, R("Tessera Labs", "Software Engineering Intern, Full Stack"))
    assert not harper.already_tracked(apps, R("Quora", "Machine Learning Engineer, New Grad"))  # different role
    assert not harper.already_tracked(apps, R("Adobe", "Machine Learning Engineer"))  # full-time vs intern
    assert harper.already_tracked(apps, R("Herald", "Software Engineer, AI Products", "baae5204-5ab6-5656-a5b4-3823bdb9dba9"))


def test_no_roles_in_status_emails():
    assert harper.parse("Hi Alex Kim, Thanks for completing your 5-minute career interview.") == []
    assert harper.parse("I didn't find a role that sufficiently matched your search. See all: https://matchharper.com/career/history?historyTab=new") == []
