"""Fill the database with fictional demo data.

Usage:  python -m scripts.seed_demo          (adds data if the DB has no leads)
        python -m scripts.seed_demo --reset  (deletes ALL leads first)

All names, companies and emails are fictional (example.com domains).
"""

import random
import sys
from datetime import timedelta

from sqlalchemy import delete, func, select

from app.database import SessionLocal, init_db
from app.models import Activity, DraftStatus, EmailDraft, FollowUp, FollowUpStatus, Lead, LeadStatus, utcnow
from app.security import ensure_admin_user

random.seed(42)

LEADS = [
    ("Ayesha Siddiqui", "Bright Path Academy", "Website", 1800),
    ("Hamza Malik", "Malik Motors", "Referral", 2500),
    ("Sara Ahmed", "Nova Foods", "LinkedIn", 3200),
    ("Bilal Khan", "UrbanNest Realty", "Upwork", 4500),
    ("Fatima Noor", "GreenLeaf Pharmacy", "Website", 1200),
    ("Usman Tariq", "Tariq Textiles", "Cold email", 6000),
    ("Zainab Raza", "Raza Dental Clinic", "Referral", 1500),
    ("Ali Hassan", "SwiftShip Logistics", "LinkedIn", 7500),
    ("Mariam Javed", "Bloom Boutique", "Website", 900),
    ("Omar Farooq", "CloudKitchen PK", "Upwork", 2800),
    ("Hira Shah", "Shah Consultants", "LinkedIn", 3900),
    ("Daniyal Qureshi", "FitZone Gyms", "Cold email", 2100),
    ("Emma Collins", "Northwind Analytics", "LinkedIn", 8800),
    ("Liam Turner", "Turner & Co Law", "Website", 5400),
    ("Noah Becker", "Becker Solar GmbH", "Referral", 9600),
    ("Sophia Rossi", "Rossi Interiors", "Upwork", 2300),
    ("Ahmed Al-Mansoori", "Desert Rose Hotels", "LinkedIn", 12000),
    ("Ravi Menon", "Menon Electronics", "Cold email", 3100),
]
STATUS_WEIGHTS = [
    (LeadStatus.NEW, 4), (LeadStatus.CONTACTED, 4), (LeadStatus.QUALIFIED, 3),
    (LeadStatus.PROPOSAL, 3), (LeadStatus.WON, 3), (LeadStatus.LOST, 2),
]
NOTES = [
    "Interested in a WhatsApp chatbot for customer queries.",
    "Wants a sales dashboard connected to their POS data.",
    "Asked for an AI email assistant for their support team.",
    "Needs lead tracking automation; currently uses spreadsheets.",
    "Exploring a booking system with automated reminders.",
]


def seed(reset: bool = False) -> None:
    init_db()
    with SessionLocal() as db:
        ensure_admin_user(db)
        if reset:
            db.execute(delete(Lead))
            db.commit()
        elif db.scalar(select(func.count()).select_from(Lead)):
            print("Database already has leads. Use --reset to replace them.")
            return

        now = utcnow()
        statuses = [s for s, w in STATUS_WEIGHTS for _ in range(w)]
        for i, (name, company, source, value) in enumerate(LEADS):
            status = statuses[i % len(statuses)]
            created = now - timedelta(days=random.randint(1, 170), hours=random.randint(0, 23))
            first = name.split()[0].lower()
            domain = company.lower().replace(" & ", "").replace(" ", "") + ".example.com"
            lead = Lead(name=name, email=f"{first}@{domain}", phone=f"+92 300 {random.randint(1000000, 9999999)}",
                        company=company, source=source, status=status, estimated_value=value,
                        notes=random.choice(NOTES), created_at=created, updated_at=created)
            db.add(lead)
            db.flush()
            db.add(Activity(lead_id=lead.id, kind="created", description="Lead created (demo data).", created_at=created))
            if status != LeadStatus.NEW:
                db.add(Activity(lead_id=lead.id, kind="call", created_at=created + timedelta(days=2),
                                description="Discovery call: discussed goals and current tools."))

            if status in LeadStatus.closed():
                db.add(FollowUp(lead_id=lead.id, scheduled_at=created + timedelta(days=5), channel="email",
                                status=FollowUpStatus.COMPLETED, completed_at=created + timedelta(days=5),
                                note="Sent proposal"))
                if status == LeadStatus.WON:
                    db.add(EmailDraft(lead_id=lead.id, subject=f"Welcome aboard, {name.split()[0]}!",
                                      body="Thanks for choosing TechNest Nova. Kickoff details to follow.",
                                      generated_by="template", status=DraftStatus.SENT,
                                      sent_to="test-inbox@example.com", sent_at=created + timedelta(days=9)))
            else:
                # Mix of overdue, upcoming and later follow-ups.
                offset = random.choice([-3, -1, 1, 2, 4, 6, 10])
                db.add(FollowUp(lead_id=lead.id, scheduled_at=now + timedelta(days=offset, hours=random.randint(1, 8)),
                                channel=random.choice(["email", "call", "whatsapp", "meeting"]),
                                note=random.choice(["Check proposal feedback", "Share case study",
                                                    "Confirm demo time", "Send pricing options"])))
        db.commit()
        print(f"Seeded {len(LEADS)} demo leads.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
