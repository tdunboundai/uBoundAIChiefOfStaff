from __future__ import annotations

from uboundai_gtm.bots.audit_bot import AuditReport, ModelResult
from uboundai_gtm.bots.outreach_bot import OutreachBot
from uboundai_gtm.llm.base import LLMRequestError

CONTACT = {"name": "Sarah Kim", "email": "sarah@acmeoutdoor.com"}


def _report(results):
    return AuditReport(domain="acmeoutdoor.com", brand_name="Acme Outdoor", results=results, flagged_issues=[])


def test_template_fallback_when_no_copy_client():
    report = _report([
        ModelResult(provider="claude", mentioned=False, sentiment="neutral", share_of_voice=0.0),
        ModelResult(provider="gemini", mentioned=False, sentiment="neutral", share_of_voice=0.0),
    ])
    package = OutreachBot(copy_client=None).generate(report, CONTACT, "duffel bags")

    assert package.personalization_source == "template"
    assert "Sarah" in package.email_body
    assert "none of the 2 AI assistants" in package.email_body
    assert package.to_email == "sarah@acmeoutdoor.com"


def test_llm_copy_client_used_when_available(fake_client):
    report = _report([ModelResult(provider="claude", mentioned=True, sentiment="positive", share_of_voice=1.0)])
    client = fake_client("claude", "A hand-written, personalized email body.")
    package = OutreachBot(copy_client=client).generate(report, CONTACT, "duffel bags")

    assert package.personalization_source == "llm"
    assert package.email_body == "A hand-written, personalized email body."
    assert len(client.calls) == 1


def test_falls_back_to_template_when_llm_call_fails(fake_client):
    report = _report([ModelResult(provider="claude", mentioned=False, sentiment="neutral", share_of_voice=0.0)])
    client = fake_client("claude", LLMRequestError("down"))
    package = OutreachBot(copy_client=client).generate(report, CONTACT, "duffel bags")

    assert package.personalization_source == "template"
    assert "Sarah" in package.email_body


def test_hook_mentions_unmentioned_models_by_name():
    report = _report([
        ModelResult(provider="claude", mentioned=False, sentiment="neutral", share_of_voice=0.0),
        ModelResult(provider="gemini", mentioned=True, sentiment="neutral", share_of_voice=0.8),
    ])
    package = OutreachBot().generate(report, CONTACT, "duffel bags")
    assert "claude" in package.linkedin_dm


def test_skipped_models_are_never_claimed_as_a_visibility_gap():
    """Regression test for a real bug: an unaudited model (no API key) was
    being counted as "doesn't mention the brand", producing a false claim
    like "4 of 5 AI assistants don't mention you" when 4 were never asked."""
    report = _report([
        ModelResult(provider="claude", mentioned=False, sentiment="neutral", share_of_voice=0.0, skipped=True),
        ModelResult(provider="chatgpt", mentioned=False, sentiment="neutral", share_of_voice=0.0, skipped=True),
        ModelResult(provider="gemini", mentioned=True, sentiment="positive", share_of_voice=0.33,
                    note="Fenty Beauty mentioned more prominently"),
        ModelResult(provider="grok", mentioned=False, sentiment="neutral", share_of_voice=0.0, skipped=True),
        ModelResult(provider="perplexity", mentioned=False, sentiment="neutral", share_of_voice=0.0, skipped=True),
    ])
    package = OutreachBot().generate(report, CONTACT, "cosmetics")

    assert "4 of 5" not in package.email_body
    assert "don't mention" not in package.email_body
    assert "Fenty Beauty" in package.email_body
    # Only the actually-audited provider should be named as "asked".
    assert "Gemini" in package.email_body
    for unaudited in ("ChatGPT", "Grok", "Perplexity", "Claude"):
        assert unaudited not in package.email_body


def test_all_models_skipped_produces_an_honest_placeholder_hook():
    report = _report([
        ModelResult(provider="claude", mentioned=False, sentiment="neutral", share_of_voice=0.0, skipped=True),
    ])
    package = OutreachBot().generate(report, CONTACT, "duffel bags")
    assert "haven't been able to check" in package.email_body
    assert report.overall_score == 0


def test_coverage_note_never_leaks_into_generated_copy():
    """Regression test for a real bug: a partial-audit's technical coverage_note
    (raw provider error text, e.g. a 429 with the request URL in it) got glued
    onto `note` and quoted verbatim in outreach copy. Outreach must only ever
    read `.note` — never `.coverage_note` — no matter what's in it."""
    report = _report([
        ModelResult(
            provider="gemini", mentioned=True, sentiment="positive", share_of_voice=0.31,
            note="NYX mentioned more prominently",
            coverage_note=(
                "stopped after 10/15 intents: Google request failed: 429 Client Error: "
                "Too Many Requests for url: https://generativelanguage.googleapis.com/"
                "v1beta/models/gemini-2.5-flash:generateContent?key=super-secret-value"
            ),
        ),
    ])
    package = OutreachBot().generate(report, CONTACT, "cosmetics")

    for leaked in ("super-secret-value", "429", "Too Many Requests", "stopped after", "Client Error"):
        assert leaked not in package.email_body
        assert leaked not in package.linkedin_dm
    assert "NYX" in package.email_body


def test_never_sends_anything_just_returns_data():
    report = _report([ModelResult(provider="claude", mentioned=True, sentiment="positive", share_of_voice=1.0)])
    package = OutreachBot().generate(report, CONTACT, "duffel bags")
    # OutreachPackage is a plain dataclass with no send/dispatch method.
    assert not hasattr(package, "send")
