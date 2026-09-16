"""Bot 3 — Outreach & Content-Personalization Bot.

Turns an Audit-Generation Bot report into a personalized pitch: a cold email,
a LinkedIn DM, ad copy, and a landing-page headline, all built from the same
real finding rather than generic copywriting.

Content generation only. This bot has no send integration by design — it
returns an `OutreachPackage`, never dispatches anything.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..llm.base import LLMClient, LLMRequestError, MissingAPIKeyError
from .audit_bot import AuditReport


@dataclass
class OutreachPackage:
    to_email: str
    subject: str
    email_body: str
    linkedin_dm: str
    ad_headline: str
    ad_body: str
    landing_headline: str
    personalization_source: str  # "llm" | "template"

    def to_dict(self) -> dict:
        return {
            "to_email": self.to_email,
            "subject": self.subject,
            "email_body": self.email_body,
            "linkedin_dm": self.linkedin_dm,
            "ad_headline": self.ad_headline,
            "ad_body": self.ad_body,
            "landing_headline": self.landing_headline,
            "personalization_source": self.personalization_source,
        }


class OutreachBot:
    def __init__(self, copy_client: LLMClient | None = None):
        """`copy_client` is optional — when given, it's used to write a more
        natural email body from the audit's real finding; on any failure (or
        when omitted) a deterministic template takes over so this bot always
        produces output."""
        self.copy_client = copy_client

    def generate(self, audit: AuditReport, contact: dict, product_category: str) -> OutreachPackage:
        hook = _build_hook(audit)
        first_name = (contact.get("name") or "there").split(" ")[0]

        email_body, source = self._email_body(product_category, hook, first_name)

        return OutreachPackage(
            to_email=contact.get("email", ""),
            subject=_subject(audit),
            email_body=email_body,
            linkedin_dm=_linkedin_dm(hook),
            ad_headline="Is AI recommending your competitor?",
            ad_body=f"Free AI visibility check for Shopify {product_category} brands.",
            landing_headline="Your customers are asking AI where to buy this. Is it recommending you?",
            personalization_source=source,
        )

    def _email_body(self, product_category: str, hook: str, first_name: str) -> tuple[str, str]:
        if self.copy_client is not None:
            try:
                answer = self.copy_client.ask(_copy_prompt(product_category, hook, first_name))
                text = answer.text.strip()
                if text:
                    return text, "llm"
            except (MissingAPIKeyError, LLMRequestError):
                pass
        return _template_email_body(product_category, hook, first_name), "template"


def _build_hook(audit: AuditReport) -> str:
    models_checked = len(audit.results)
    unmentioned = [r.provider for r in audit.results if not r.mentioned]

    if models_checked and len(unmentioned) == models_checked:
        return f"none of the {models_checked} AI assistants we checked mention {audit.brand_name} at all"
    if unmentioned:
        return (
            f"{len(unmentioned)} of {models_checked} AI assistants "
            f"({', '.join(unmentioned)}) don't mention {audit.brand_name} at all"
        )
    weakest = audit.weakest_result
    if weakest and weakest.note:
        return f"on {weakest.provider}, {weakest.note.lower()}"
    return f"{audit.brand_name}'s share of voice across {models_checked} AI assistants has room to grow"


def _subject(audit: AuditReport) -> str:
    if audit.mentioned_count < len(audit.results):
        return "An AI shopping assistant is sending your customers to a competitor instead of you"
    return f"How {audit.brand_name} shows up when customers ask AI where to buy"


def _linkedin_dm(hook: str) -> str:
    return f"Ran your store through 5 AI shopping assistants — {hook}. Worth a look?"


def _template_email_body(product_category: str, hook: str, first_name: str) -> str:
    return (
        f"Hi {first_name} — we asked Gemini, ChatGPT, Perplexity, Grok and Claude "
        f"where to buy {product_category}. {hook}.\n\n"
        f"We ran a full AI visibility audit on your store — happy to share it, no strings attached."
    )


def _copy_prompt(product_category: str, hook: str, first_name: str) -> str:
    return (
        "Write a short, direct cold outreach email (3-4 sentences, no subject line) "
        f"to {first_name}, the owner of a Shopify brand selling {product_category}. "
        f"Use this real finding as the hook: {hook}. "
        "End with an offer to share the full AI visibility audit, no strings attached. "
        "Plain text only, no markdown."
    )
