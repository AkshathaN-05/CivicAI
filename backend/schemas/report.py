"""Pydantic schemas for report endpoints — Part A §7, §18."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums — mirror Part A §7 issue_category and complaint_status
# ---------------------------------------------------------------------------

class IssueCategory(str, Enum):
    pothole = "pothole"
    waterlogging = "waterlogging"
    broken_streetlight = "broken_streetlight"
    garbage_overflow = "garbage_overflow"
    open_drain = "open_drain"
    illegal_construction = "illegal_construction"
    water_supply = "water_supply"
    sewage = "sewage"
    road_damage = "road_damage"
    other = "other"


CATEGORY_LABELS: dict[str, str] = {
    "pothole": "Pothole",
    "waterlogging": "Waterlogging",
    "broken_streetlight": "Broken Streetlight",
    "garbage_overflow": "Garbage Overflow",
    "open_drain": "Open Drain",
    "illegal_construction": "Illegal Construction",
    "water_supply": "Water Supply",
    "sewage": "Sewage",
    "road_damage": "Road Damage",
    "other": "Other",
}


class ReportStatus(str, Enum):
    submitted = "SUBMITTED"
    under_review = "UNDER_REVIEW"
    resolved = "RESOLVED"
    rejected = "REJECTED"
    archived = "ARCHIVED"


# ---------------------------------------------------------------------------
# Authority sub-schema
# ---------------------------------------------------------------------------

class AuthorityOut(BaseModel):
    id: str
    name: str
    short_name: str
    contact_email: str
    phone: str


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class ReportCreate(BaseModel):
    category: IssueCategory
    area_text: str = Field(..., min_length=2, max_length=500)
    description: str = Field(..., min_length=10, max_length=2000)

    @field_validator("area_text", "description", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class ReportOut(BaseModel):
    report_id: str
    category: IssueCategory
    category_label: str
    area_text: str
    description: str
    status: ReportStatus
    recommended_authority: Optional[AuthorityOut] = None
    match_reason: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    created_at: datetime
    photo_filename: Optional[str] = None


class ReportListOut(BaseModel):
    reports: list[ReportOut]
    total: int
