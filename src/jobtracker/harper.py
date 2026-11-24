"""Read job recommendations out of Harper (matchharper.com) digest emails.

Harper writes each role in one of a few shapes, always followed by a matchharper.com link
with an `id=`:
    Quora · Machine Learning Engineer, New Grad (https://matchharper.com/…id=…) — summary
    - Kitewire · Applied Scientist Intern: https://matchharper.com/…id=… — summary
    The closest overlap is Software Engineer at Pryzm: https://matchharper.com/…id=…. summary
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .classify import role_similarity, same_company

HARPER_DOMAIN = "matchharper.com"

LINK = re.compile(r"\(?(https://matchharper\.com/career/history\?[^\s)]*?\bid=([0-9a-f-]{36}))\)?")
# Text before a role title that isn't part of it ("The closest overlap is", "For comparison,", "- Fintech:")
LEAD = re.compile(
    r"(?:[.:;!?]\s+|\bis\s+|\bexplore\s+|\bwhile\s+|,\s+and\s+|^[\s,\-–—•*]+"
    r"|\b[Ff]or [\w\- ]{2,40},\s+|\b[Oo]n the [\w\- ]{2,30},\s+)"
)
EMPLOYER = re.compile(r"Employer posting \((https?://[^)\s]+)\)")


@dataclass
class HarperRole:
    company: str
    role: str
    harper_id: str
    harper_url: str
    employer_url: str
    summary: str

    @property
    def is_internship(self) -> bool:
        return is_intern(self.role)


def is_intern(role: str) -> bool:
    return bool(re.search(r"\b(intern|internship|co-?op)\b", role or "", re.I))


def _tidy(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" \t-–—•*:,.")


def _title(head: str) -> tuple[str, str, str]:
    """(company, role, the literal title text) from the text just before a Harper link."""
    if " · " in head:
        left, _, right = head.rpartition(" · ")
        left = LEAD.split(left)[-1]
        return _tidy(left), _tidy(right), f"{left} · {right}"
    if " at " in head:
        left, _, right = head.rpartition(" at ")
        role = LEAD.split(left)[-1]
        return _tidy(right), _tidy(role), f"{role} at {right}"
    return "", "", ""


def parse(body: str) -> list[HarperRole]:
    text = (body or "").replace("\\[", "[").replace("\\]", "]")
    links = list(LINK.finditer(text))
    titles = []
    for i, m in enumerate(links):
        start = links[i - 1].end() if i else 0
        head = text[start:m.start()].split("\n")[-1].rstrip(" :(\t")
        titles.append(_title(head))
    out: list[HarperRole] = []
    seen: set[str] = set()
    for i, m in enumerate(links):
        company, role, _ = titles[i]
        hid = m.group(2)
        if not company or not role or len(company) > 60 or len(role) > 160 or hid in seen:
            continue
        seen.add(hid)
        end = links[i + 1].start() if i + 1 < len(links) else len(text)
        if i + 1 < len(links) and titles[i + 1][2]:
            cut = text.rfind(titles[i + 1][2].strip(), m.end(), end)
            if cut != -1:
                end = cut  # items sharing a paragraph: stop before the next title
        tail = text[m.end():end]
        emp = EMPLOYER.search(tail)
        summary = EMPLOYER.sub("", tail.split("\n\n")[0].split("\n- ")[0])
        summary = re.sub(r"^[\s.)]*[—:–-]?\s*", "", summary)
        summary = _tidy(summary)[:420]
        out.append(HarperRole(company=company[:1].upper() + company[1:], role=role, harper_id=hid,
                              harper_url=m.group(1), employer_url=emp.group(1) if emp else "", summary=summary))
    return out


def _stem(s: str) -> str:
    return re.sub(r"er\b", "", re.sub(r"ing\b", "", (s or "").lower()))


def already_tracked(apps: list[dict], r: HarperRole) -> bool:
    """True if this recommendation is already a card (same Harper id, or same company + role)."""
    for a in apps:
        blob = f"{a.get('notes', '')} {a.get('url', '')}"
        if r.harper_id in blob:
            return True
        if (same_company(a.get("company", ""), r.company)
                and is_intern(a.get("role", "")) == r.is_internship
                and role_similarity(_stem(a.get("role", "")), _stem(r.role)) >= 0.75):
            return True
    return False


def to_application(r: HarperRole, day: str) -> dict:
    notes = f"Recommended by Harper ({day}). {r.summary}".strip()
    notes += f"\nHarper: {r.harper_url}"
    return {"company": r.company, "role": r.role, "stage": "wishlist", "source": "Harper",
            "type": "Internship" if r.is_internship else "Full-time",
            "url": r.employer_url or r.harper_url, "notes": notes[:2000],
            "events": [{"date": day, "kind": "note", "stage": "", "text": "Recommended by Harper"}]}
