"""Request/response shapes. Field names match the web UI (camelCase)."""

from __future__ import annotations

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Stage = Literal[
    "wishlist", "applied", "assessment", "interview",
    "offer", "rejected", "withdrawn", "ghosted",
]


def _blank_to_none(v):
    if isinstance(v, str) and not v.strip():
        return None
    return v


class Event(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: dt.date
    kind: Literal["stage", "note"]
    stage: Stage | None = None
    text: str = Field(default="", max_length=2000)

    _blank_stage = field_validator("stage", mode="before")(_blank_to_none)

    @model_validator(mode="after")
    def stage_events_need_a_stage(self) -> "Event":
        if self.kind == "stage" and self.stage is None:
            raise ValueError("a stage event must name the stage")
        return self


class ApplicationIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=300)
    stage: Stage = "wishlist"
    type: str = Field(default="", max_length=50)
    sector: str = Field(default="", max_length=50)
    location: str = Field(default="", max_length=200)
    mode: str = Field(default="", max_length=50)
    salary: str = Field(default="", max_length=100)
    appliedDate: dt.date | None = None
    deadline: dt.date | None = None
    followUp: dt.date | None = None
    nextStep: str = Field(default="", max_length=300)
    source: str = Field(default="", max_length=100)
    referral: str = Field(default="", max_length=200)
    contact: str = Field(default="", max_length=300)
    url: str = Field(default="", max_length=2000)
    resume: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=20000)
    events: list[Event] = Field(default_factory=list, max_length=500)
    createdAt: int | None = None  # epoch milliseconds, optional

    _blank_dates = field_validator("appliedDate", "deadline", "followUp", mode="before")(_blank_to_none)

    @field_validator("company")
    @classmethod
    def company_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company is required")
        return v


class BulkItem(ApplicationIn):
    id: UUID | None = None


class ExtractIn(BaseModel):
    text: str = Field(min_length=40, max_length=60000)


class GmailSyncIn(BaseModel):
    since: dt.date | None = None
