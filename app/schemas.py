"""Pydantic schemas: validate request bodies and shape API responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import DraftStatus, FollowUpStatus, LeadStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: int
    email: EmailStr
    full_name: str


# ---------- Leads ----------
class LeadBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=60)
    estimated_value: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name", "phone", "company", "source", "notes", mode="before")
    @classmethod
    def strip_text(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class LeadCreate(LeadBase):
    status: LeadStatus = LeadStatus.NEW


class LeadUpdate(BaseModel):
    """All fields optional: only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=60)
    status: LeadStatus | None = None
    estimated_value: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=5000)


class LeadOut(ORMModel):
    id: int
    name: str
    email: EmailStr
    phone: str | None
    company: str | None
    source: str | None
    status: LeadStatus
    estimated_value: float | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    next_follow_up: datetime | None = None


class LeadPage(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    page_size: int


# ---------- Follow-ups ----------
class FollowUpCreate(BaseModel):
    scheduled_at: datetime
    channel: str = Field(default="email", pattern="^(email|call|whatsapp|meeting)$")
    note: str | None = Field(default=None, max_length=2000)


class FollowUpUpdate(BaseModel):
    scheduled_at: datetime | None = None
    channel: str | None = Field(default=None, pattern="^(email|call|whatsapp|meeting)$")
    note: str | None = Field(default=None, max_length=2000)


class FollowUpOut(ORMModel):
    id: int
    lead_id: int
    scheduled_at: datetime
    channel: str
    note: str | None
    status: FollowUpStatus
    processed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    lead_name: str | None = None
    lead_company: str | None = None


# ---------- Email drafts ----------
class DraftGenerate(BaseModel):
    purpose: str = Field(default="follow-up", max_length=200)
    extra_context: str | None = Field(default=None, max_length=2000)
    follow_up_id: int | None = None


class DraftUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=20000)


class DraftOut(ORMModel):
    id: int
    lead_id: int
    follow_up_id: int | None
    subject: str
    body: str
    generated_by: str
    status: DraftStatus
    sent_to: str | None
    sent_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime


# ---------- Activity ----------
class ActivityOut(ORMModel):
    id: int
    lead_id: int
    kind: str
    description: str
    created_at: datetime


class ActivityCreate(BaseModel):
    kind: str = Field(default="note", pattern="^(note|call|meeting|email)$")
    description: str = Field(min_length=1, max_length=5000)


# ---------- Analytics ----------
class DashboardStats(BaseModel):
    total_leads: int
    open_leads: int
    won: int
    lost: int
    conversion_rate: float  # won / (won + lost) * 100
    win_rate_overall: float  # won / total * 100
    pipeline_value: float
    won_value: float
    by_status: dict[str, int]
    by_source: dict[str, int]
    leads_per_month: list[dict]
    upcoming_follow_ups: int
    overdue_follow_ups: int
    due_follow_ups: int
