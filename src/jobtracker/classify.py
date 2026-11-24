"""Turn a job-related email into (kind, company, role). Pure functions, no I/O.

kind is one of: applied, assessment, interview, offer, rejected, viewed, other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STAGE_RANK = {"applied": 1, "assessment": 2, "interview": 3, "offer": 4}

# --- phrase lists ---------------------------------------------------------

OFFER = re.compile(r"\b(offer letter|pleased to (extend|offer)|extend(ing)? (you )?an offer|offer of employment)\b", re.I)

# Strong phrases mean rejection even inside an otherwise friendly email.
REJECT_STRONG = re.compile(
    r"(not (to |be )?mov(e|ing) forward with your (application|candidacy)"
    r"|(decided|chosen|elected) to (pursue|move forward with|proceed with) other"
    r"|regret to inform"
    r"|(have|has) not been selected"
    r"|were not selected|was not selected|wasn'?t selected"
    r"|will not be (moving forward|proceeding|progressing)"
    r"|not (be )?proceeding with your application"
    r"|no longer (being )?consider(ed|ing) (you|your)"
    r"|position (has|had) (now )?been filled|this position has now been filled"
    r"|(have )?closed the .{0,60}position and will not be filling"
    r"|decided not to (move forward|proceed|advance))",
    re.I,
)
# Weak phrases only count when the email isn't an application confirmation.
REJECT_WEAK = re.compile(r"\b(unfortunately|other candidates|not a match|not the right fit|after careful consideration)\b", re.I)

ASSESSMENT = re.compile(
    r"(codesignal|hackerrank|codility|hirevue|criteria ?corp|criteria assessment|online assessment|coding assessment"
    r"|technical assessment|coding challenge|take[- ]home|pre[- ]recorded video interview|entry-level assessment"
    r"|complete (the|our|an?|your) [\w -]{0,30}(assessment|test)\b)",
    re.I,
)
ASSESSMENT_DONE = re.compile(r"(assessment completed|you have completed the|completed your assessment)", re.I)

# Scheduling language wins over an assessment mention ("thanks for finishing the HackerRank, let's set up an interview").
INTERVIEW_STRONG = re.compile(
    r"(schedule (an? |your |a time for )?interview|interview (invitation|invite|request)|set up an interview"
    r"|invit(e|ing) you to (an? )?(interview|phone screen|superday|onsite)|your availability for (an? )?interview"
    r"|phone screen|superday)",
    re.I,
)
INTERVIEW = re.compile(
    r"((video|phone|virtual|technical|final|onsite|on-site|zoom|teams) interview\b"
    r"|\binterview with\b"
    r"|schedule (an? |your |a time for )?(interview|call|chat|conversation)"
    r"|interview (invitation|invite|request|confirmation)"
    r"|invit(e|ing) you to (an? )?(interview|phone screen|video interview|superday|onsite)"
    r"|set up an interview|like to (set up|schedule) (an? )?(interview|call|time)"
    r"|phone screen|next round|superday|on-?site interview|interview with the hiring manager"
    r"|your availability for (an? )?(interview|call))",
    re.I,
)

CONFIRM = re.compile(
    r"(thank(s| you) (so much |very much )?for (applying|your application|submitting|your recent application|taking the time to apply|completing your application)"
    r"|received your (application|resume)|we got your application"
    r"|application (has been |was )?(successfully )?(received|submitted)"
    r"|your application was sent to|indeed application:|resume has been successfully submitted"
    r"|we('ve| have) received your application|confirm(ing)? (that )?we('ve| have)? received)",
    re.I,
)

VIEWED = re.compile(r"your application was viewed by", re.I)

# --- company / role extraction -------------------------------------------

GENERIC_NAMES = re.compile(
    r"^(workday|workday notify.*|linkedin|indeed( apply)?|handshake|greenhouse|lever|ashby|icims|jobvite|smartrecruiters"
    r"|do[- ]?not[- ]?reply.*|no[- ]?reply|noreply|notifications?|careers?|recruiting|talent acquisition|human resources"
    r"|hr|application received|google calendar|automationmanager.*)$",
    re.I,
)
NAME_SUFFIX = re.compile(
    r"\s*(\||-|@).*$"  # "Medpace, Inc. @ icims"
    r"|\s+(hiring|talent|recruiting|recruitment|campus recruiting|early talent|careers|talent acquisition|hr|human resources|people)( team)?$",
    re.I,
)
ATS_DOMAINS = ("greenhouse", "ashbyhq", "lever.co", "icims", "jobvite", "smartrecruiters", "workday", "myworkday",
               "taleo", "successfactors", "brassring", "oraclecloud", "tal.net", "teamtailor", "linkedin", "indeed",
               "joinhandshake", "hackerrank", "codesignal", "codility", "criteriacorp", "jobmail", "yello", "gmail")

ROLE_WORDS = r"(?:position|role|opening|job|internship|program)"

COMPANY_PATTERNS_SUBJECT = [
    re.compile(r"your application was (?:sent to|viewed by) (?P<company>.+)$", re.I),
    re.compile(r"your application (?:to |for |\s*[-–:]\s*)(?P<role>.+?) at (?P<company>.+)$", re.I),
    re.compile(r"assessment completed:\s*(?P<company>(?-i:[A-Z])[\w&.' ]{1,40}?)\s+(?:\d{4}\s+)?(?:\w+\s+)?assessment", re.I),
    re.compile(r"^(?P<company>(?-i:[A-Z])[\w&.' ]{1,40}?) (?:invited you|is waiting for your)", re.I),
    re.compile(r"(?:application|applying) for (?P<role>.+?) at (?P<company>[^|!]+)$", re.I),
    re.compile(r"(?:applying|applied|application) (?:to|at|with) (?P<company>(?-i:[A-Z])[\w&.,' ]{1,50}?)\s*(?:!|$|\||-|–|\()", re.I),
    re.compile(r"interest in (?P<company>(?-i:[A-Z])[\w&.,' ]{1,50}?)\s*(?:!|$|\.)", re.I),
    re.compile(r"^(?P<company>(?-i:[A-Z])[\w&.' ]{1,40}?) (?:\||-|–) ", re.I),          # "Kitewire | Confirmation…"
    re.compile(r"^(?P<company>(?-i:[A-Z])[\w&.' ]{1,40}?) application(?: update| status)?\b", re.I),  # "Holloway Application Update"
]
COMPANY_PATTERNS_BODY = [
    re.compile(r"items were sent to (?P<company>.+?)\.\s*good luck", re.I),        # Indeed
    re.compile(r"(?:position|role|opening|internship) (?:of |of the )?(?P<role>[^.]{3,110}?) at (?P<company>(?-i:[A-Z])[\w&.,' ]{1,60}?)(?:[.!,]| and | we |\s+-)", re.I),
    re.compile(r"(?:applying|applied|application|apply) (?:to|for) (?:the |our )?(?P<role>[^.]{3,110}?) (?:" + ROLE_WORDS + r" )?at (?P<company>(?-i:[A-Z])[\w&.,' ]{1,60}?)(?:[.!,]| and | we |\s+-)", re.I),
    re.compile(r"(?:position|role|opening) at (?P<company>(?-i:[A-Z])[\w&.,' ]{1,60}?)(?:[.!,]| and | we |\s+-)", re.I),
    re.compile(r"thank(?:s| you) for (?:applying|your interest|your application) (?:to|in|with) (?P<company>(?-i:[A-Z])[\w&.' ]{1,50}?)(?:[.!,]|'s| and )", re.I),
    re.compile(r"interest in (?:joining |a career (?:at|with) |career opportunities (?:at|with) )?(?P<company>(?-i:[A-Z])[\w&.' ]{1,50}?)(?:[.!,]| and )", re.I),
]
ROLE_PATTERNS = [
    re.compile(r"indeed application: (?P<role>.+)$", re.I),
    re.compile(r"(?:position of|position:|role of) (?P<role>[^.\n]{3,110}?)(?:[.,;]| at |\s+job\b)", re.I),
    re.compile(r"(?:for|to|in) (?:the|our) (?P<role>[^.\n]{3,110}?) " + ROLE_WORDS + r"\b", re.I),
    re.compile(r"application for (?:the )?(?P<role>[^.\n]{3,110}?)(?: role| position)?(?: at |[.,]| has)", re.I),
]
BAD_COMPANY = re.compile(
    r"^(us|our|the|a|this|your|you|our team|the team|the position|the role|joining|we|it)$"
    r"|^(thank|thanks|your|re:|fwd?:|invitation|reminder|update|confirmation|action required|next steps|important"
    r"|hi|hello|dear|hey|application|congratulations"
    r"|indeed|linkedin|handshake|workday|codesignal|hackerrank|codility|hirevue|greenhouse|ashby|jobvite)\b", re.I)
FREEMAIL = ("gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "aol.com", "proton.me")


STATUS_WORDS = re.compile(r"\b(interview|invitation|invite|assessment|application|update|confirmation|reminder|status|next steps?|offer|thank)\b", re.I)


def _ok(company: str) -> bool:
    return bool(company) and not BAD_COMPANY.match(company) and not STATUS_WORDS.search(company)


@dataclass
class Classified:
    kind: str
    company: str
    role: str
    stage: str | None  # stage this email implies, if any


def _clean(s: str | None) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip(" .,:;!-–|\"'")
    return s[:200]


def _domain_company(address: str) -> str:
    addr = (address or "").lower()
    local, _, domain = addr.partition("@")
    if not domain or domain in FREEMAIL or any(a in domain for a in ATS_DOMAINS):
        return ""
    parts = [p for p in domain.split(".") if p not in ("mail", "email", "careers", "jobs", "recruiting", "jobalerts", "people", "talent", "hr", "notifications")]
    core = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
    if core in ("co", "com", "org", "net", ""):
        return ""
    return core.upper() if len(core) <= 4 else core.capitalize()


def company_from_sender(display_name: str, address: str) -> str:
    dom = _domain_company(address)
    if dom:
        return dom
    name = _clean(display_name)
    if name:
        m = re.match(r"^recruiting at (.+)$", name, re.I)
        if m:
            name = m.group(1)
        name = _clean(NAME_SUFFIX.sub("", name))
        if name and not GENERIC_NAMES.match(name) and "@" not in name:
            return name
    addr = (address or "").lower()
    local, _, domain = addr.partition("@")
    if "myworkday.com" in domain or "icims.com" in domain:
        base = local.split("+")[0]
        if base and not re.match(r"^(no-?reply|do-?not-?reply|wd\d*|notify)$", base):
            return base.upper() if len(base) <= 4 else base.capitalize()
    return ""


def extract_company_role(subject: str, body: str, display_name: str, address: str) -> tuple[str, str]:
    subj = _clean(subject)
    text = re.sub(r"\s+", " ", body or "")[:4000]
    company = role = ""
    for pat in COMPANY_PATTERNS_SUBJECT:
        m = pat.search(subj)
        if m and _ok(_clean(m.groupdict().get("company"))):
            company = _clean(m.groupdict().get("company"))
            role = role or _clean(m.groupdict().get("role"))
            break
    if not company or not role:
        for pat in COMPANY_PATTERNS_BODY:
            m = pat.search(text)
            if m:
                cand = _clean(m.groupdict().get("company"))
                if not company and _ok(cand):
                    company = cand
                    role = role or _clean(m.groupdict().get("role"))
                elif company and not role and cand and same_company(cand, company):
                    role = _clean(m.groupdict().get("role"))
                if company and role:
                    break
    if not role:
        for pat in ROLE_PATTERNS:
            m = pat.search(subj) or pat.search(text)
            if m:
                role = _clean(m.group("role"))
                break
    if not _ok(company):
        company = ""
    if not company:
        company = company_from_sender(display_name, address)
    company = re.sub(r",?\s+(Inc|LLC|Ltd|Corp|Corporation)\.?$", "", company, flags=re.I)
    return company, role


# "Alex, your application was sent to X" / "Alex, thank you for applying": drop the leading first name
# so it can't be mistaken for the company.
_SALUTATION = re.compile(r"^(?:[A-Z][a-z]+ ?){1,2}, (?=(?:your|thank|thanks|you|we|congrat)\w*\b)", re.I)


def _drop_salutation(subject: str) -> str:
    return _SALUTATION.sub("", subject.strip(), count=1)


def classify(subject: str, body: str, display_name: str = "", address: str = "") -> Classified:
    blob = f"{subject}\n{body or ''}"
    confirm = bool(CONFIRM.search(blob))
    if VIEWED.search(subject):
        kind = "viewed"
    elif OFFER.search(blob):
        kind = "offer"
    elif REJECT_STRONG.search(blob) or (not confirm and REJECT_WEAK.search(blob) and not ASSESSMENT.search(blob) and not INTERVIEW.search(blob)):
        kind = "rejected"
    elif INTERVIEW_STRONG.search(blob) and not re.search(r"pre[- ]?recorded|hirevue|one[- ]way video", blob, re.I):
        kind = "interview"
    elif ASSESSMENT_DONE.search(blob):
        kind = "assessment_done"
    elif ASSESSMENT.search(blob):
        kind = "assessment"
    elif INTERVIEW.search(blob):
        kind = "interview"
    elif confirm:
        kind = "applied"
    else:
        kind = "other"
    company, role = extract_company_role(_drop_salutation(subject), body, display_name, address)
    stage = {"applied": "applied", "assessment": "assessment", "interview": "interview",
             "offer": "offer", "rejected": "rejected"}.get(kind)
    return Classified(kind=kind, company=company, role=role, stage=stage)


# --- matching ------------------------------------------------------------

_STOP = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|group|the|and|technologies|technology|holdings)\b")


def norm_company(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = _STOP.sub(" ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _words(s: str) -> tuple[str, ...]:
    s = (s or "").lower().replace("&", " and ")
    s = _STOP.sub(" ", re.sub(r"\(.*?\)", " ", s))
    return tuple(re.findall(r"[a-z0-9]+", s))


def _aliases(s: str) -> set[tuple[str, ...]]:
    out = {_words(s)} | {_words(p) for p in re.findall(r"\(([^)]+)\)", s or "")}
    return {x for x in out if x}


def same_company(a: str, b: str) -> bool:
    """Equal names, a whole-word prefix ("Centennial" / "Centennial Management"),
    or two one-word names where one starts the other ("KRW" / "Krwinc" from an email domain)."""
    for x in _aliases(a):
        for y in _aliases(b):
            if "".join(x) == "".join(y):
                return True
            short, long_ = sorted((x, y), key=len)
            if long_[:len(short)] == short:
                return True
            if len(x) == 1 and len(y) == 1:
                js, jl = sorted((x[0], y[0]), key=len)
                if len(js) >= 3 and jl.startswith(js):
                    return True
    return False


def role_similarity(a: str, b: str) -> float:
    words = lambda s: {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1 and w not in {"the", "and", "for", "of", "to"}}
    x, y = words(a), words(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)
