from __future__ import annotations

from uboundai_gtm.bots.audit_bot import AuditGenerationBot
from uboundai_gtm.bots.outreach_bot import OutreachBot
from uboundai_gtm.bots.prospecting_bot import ICPFilter, ProspectingBot
from uboundai_gtm.pipeline import run_pipeline

RAW = [
    {
        "id": "a", "store": "A", "domain": "a.com", "brand_name": "A",
        "category": "Outdoor", "monthly_revenue_est": 3_000_000,
        "competitors": [], "product_category": "tents",
        "known_facts": {}, "contact": {"name": "Al", "email": "al@a.com"},
    },
    {
        "id": "b", "store": "B", "domain": "b.com", "brand_name": "B",
        "category": "Outdoor", "monthly_revenue_est": 2_000_000,
        "competitors": [], "product_category": "tents",
        "known_facts": {}, "contact": {"name": "Bo", "email": "bo@b.com"},
    },
]


def test_pipeline_wires_prospecting_audit_and_outreach(fake_client):
    prospecting_bot = ProspectingBot(RAW)
    audit_bot = AuditGenerationBot({"claude": fake_client("claude", "no relevant mention here")})
    outreach_bot = OutreachBot()

    results = run_pipeline(
        icp=ICPFilter(categories=("Outdoor",), min_revenue=0, max_revenue=1e9),
        top_n=1,
        audit_bot=audit_bot,
        outreach_bot=outreach_bot,
        prospecting_bot=prospecting_bot,
    )

    assert len(results) == 1
    result = results[0]
    assert result.prospect.audit is result.audit
    assert result.outreach.to_email == result.prospect.contact["email"]


def test_pipeline_skips_prospects_below_top_n(fake_client):
    prospecting_bot = ProspectingBot(RAW)
    audit_bot = AuditGenerationBot({"claude": fake_client("claude", "text")})

    results = run_pipeline(
        icp=ICPFilter(categories=("Outdoor",), min_revenue=0, max_revenue=1e9),
        top_n=0,
        audit_bot=audit_bot,
        prospecting_bot=prospecting_bot,
    )
    assert results == []
