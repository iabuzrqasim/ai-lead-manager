"""SQLAlchemy ORM models (database tables)."""

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class LeadStatus(str, enum.Enum):
    NEW = "New"
    CONTACTED = "Contacted"
    QUALIFIED = "Qualified"
    PROPOSAL = "Proposal"
    WON = "Won"
    LOST = "Lost"

    @classmethod
    def closed(cls) -> set["LeadStatus"]:
        return {cls.WON, cls.LOST}


class FollowUpStatus(str, enum.Enum):
    PENDING = "Pending"
    DUE = "Due"  # picked up by the scheduler, waiting for a human
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class DraftStatus(str, enum.Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    FAILED = "Failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    company: Mapped[str | None] = mapped_column(String(120), index=True)
    source: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, values_callable=lambda e: [m.value for m in e], native_enum=False, length=20),
        default=LeadStatus.NEW,
        index=True,
    )
    estimated_value: Mapped[float | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    follow_ups: Mapped[list["FollowUp"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="FollowUp.scheduled_at"
    )
    email_drafts: Mapped[list["EmailDraft"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="EmailDraft.created_at.desc()"
    )
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Activity.created_at.desc()"
    )


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="email")
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FollowUpStatus] = mapped_column(
        Enum(FollowUpStatus, values_callable=lambda e: [m.value for m in e], native_enum=False, length=20),
        default=FollowUpStatus.PENDING,
        index=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="follow_ups")


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    follow_up_id: Mapped[int | None] = mapped_column(ForeignKey("follow_ups.id", ondelete="SET NULL"))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String(20), default="template")  # "ai" | "template" | "manual"
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus, values_callable=lambda e: [m.value for m in e], native_enum=False, length=20),
        default=DraftStatus.DRAFT,
    )
    sent_to: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="email_drafts")


class Activity(Base):
    """Timeline of everything that happened to a lead."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    lead: Mapped[Lead] = relationship(back_populates="activities")
