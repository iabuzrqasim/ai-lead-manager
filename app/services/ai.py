"""AI email-draft generation.

Uses the Anthropic Messages API when ANTHROPIC_API_KEY is set.
If no key is configured, or the API call fails, it falls back to a
built-in template so the app always keeps working.
"""

import json
import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.models import Lead

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class DraftResult:
    subject: str
    body: str
    generated_by: str  # "ai" or "template"
    warning: str | None = None


def _lead_context(lead: Lead) -> str:
    recent = [f"- {a.created_at:%Y-%m-%d} [{a.kind}] {a.description}" for a in lead.activities[:8]]
    return "\n".join(
        [
            f"Name: {lead.name}",
            f"Company: {lead.company or 'unknown'}",
            f"Status: {lead.status.value}",
            f"Source: {lead.source or 'unknown'}",
            f"Notes: {lead.notes or 'none'}",
            "Recent activity:",
            *(recent or ["- none"]),
        ]
    )


def template_draft(lead: Lead, purpose: str, sender_company: str) -> DraftResult:
    first_name = lead.name.split()[0]
    company_line = f" at {lead.company}" if lead.company else ""
    subject = f"Following up{(' - ' + lead.company) if lead.company else ''}"
    body = (
        f"Hi {first_name},\n\n"
        f"I hope you're well. I wanted to follow up on our recent conversation about how "
        f"{sender_company} can support you and the team{company_line}.\n\n"
        f"Would you have 15 minutes this week for a quick call to discuss next steps?\n\n"
        f"Best regards,\n{sender_company}"
    )
    if purpose and purpose.lower() not in {"follow-up", "followup"}:
        body = body.replace("follow up on our recent conversation", f"reach out regarding {purpose}")
    return DraftResult(subject=subject, body=body, generated_by="template")


def generate_draft(lead: Lead, purpose: str = "follow-up", extra_context: str | None = None) -> DraftResult:
    settings = get_settings()
    if not settings.ai_enabled:
        return template_draft(lead, purpose, settings.company_name)

    system = (
        f"You write short, professional B2B sales emails for {settings.company_name}, "
        "a software and AI automation agency. Be specific to the lead, friendly, and concise "
        "(under 150 words). Never invent facts, prices or meetings that are not in the context. "
        'Reply ONLY with JSON: {"subject": "...", "body": "..."}'
    )
    user_msg = f"Purpose: {purpose}\n\nLead context:\n{_lead_context(lead)}"
    if extra_context:
        user_msg += f"\n\nExtra context from the salesperson:\n{extra_context}"

    try:
        response = httpx.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": 600,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=settings.ai_timeout_seconds,
        )
        response.raise_for_status()
        text = "".join(b.get("text", "") for b in response.json().get("content", []))
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1])
        subject, body = str(data["subject"]).strip(), str(data["body"]).strip()
        if not subject or not body:
            raise ValueError("empty subject or body")
        return DraftResult(subject=subject, body=body, generated_by="ai")
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("AI draft generation failed, using template: %s", exc)
        result = template_draft(lead, purpose, settings.company_name)
        result.warning = "AI generation failed; a template draft was used instead."
        return result
