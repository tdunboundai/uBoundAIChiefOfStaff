from __future__ import annotations

from uboundai_gtm.bots.audit_bot import AuditGenerationBot
from uboundai_gtm.bots.prospecting_bot import (
    ICPFilter,
    ProspectingBot,
    ProspectStatus,
    UNKNOWN_REVENUE_SCORE,
)

RAW = [
    {
        "id": "a", "store": "A", "domain": "a.com", "brand_name": "A",
        "category": "Outdoor", "monthly_revenue_est": 3_000_000,
        "competitors": ["Riv"], "product_category": "tents",
        "known_facts": {"price_usd": 100}, "contact": {"name": "Al", "email": "al@a.com"},
    },
    {
        "id": "b", "store": "B", "domain": "b.com", "brand_name": "B",
        "category": "Beauty", "monthly_revenue_est": 15_000_000,
        "competitors": [], "product_category": "serum",
        "known_facts": {}, "contact": {"name": "Bo", "email": "bo@b.com"},
    },
    {
        "id": "c", "store": "C", "domain": "c.com", "brand_name": "C",
        "category": "Electronics", "monthly_revenue_est": 3_000_000,
        "competitors": [], "product_category": "cables",
        "known_facts": {}, "contact": {"name": "Cy", "email": "cy@c.com"},
    },
]


def test_filters_out_categories_not_in_icp():
    bot = ProspectingBot(RAW)
    records = bot.find_prospects(ICPFilter(categories=("Outdoor", "Beauty"), min_revenue=0, max_revenue=1e9))
    ids = {r.id for r in records}
    assert ids == {"a", "b"}


def test_filters_by_revenue_range():
    bot = ProspectingBot(RAW)
    records = bot.find_prospects(ICPFilter(categories=("Outdoor", "Beauty"), min_revenue=0, max_revenue=5_000_000))
    ids = {r.id for r in records}
    assert ids == {"a"}


def test_records_sorted_by_icp_score_descending():
    bot = ProspectingBot(RAW)
    records = bot.find_prospects(ICPFilter(categories=("Outdoor", "Beauty", "Electronics"), min_revenue=0, max_revenue=1e9))
    scores = [r.icp_score for r in records]
    assert scores == sorted(scores, reverse=True)


def test_default_status_is_new_with_no_audit(fake_client):
    bot = ProspectingBot(RAW)
    records = bot.find_prospects(ICPFilter(categories=("Outdoor",), min_revenue=0, max_revenue=1e9))
    assert records[0].status == ProspectStatus.NEW
    assert records[0].audit is None
    assert records[0].to_dict()["gap_note"] == "not yet audited"


def test_unknown_revenue_passes_revenue_filter_and_gets_neutral_score():
    scraped = {
        "id": "d", "store": "D", "domain": "d.com", "brand_name": "D",
        "category": "Outdoor", "monthly_revenue_est": None,
        "competitors": [], "product_category": "packs",
        "known_facts": {}, "contact": {"name": None, "email": None},
    }
    bot = ProspectingBot([scraped])
    records = bot.find_prospects(ICPFilter(categories=("Outdoor",), min_revenue=1_000_000, max_revenue=5_000_000))
    assert len(records) == 1
    assert records[0].icp_score == UNKNOWN_REVENUE_SCORE


def test_audit_top_n_runs_audit_and_sets_gap_note(fake_client):
    audit_bot = AuditGenerationBot({"claude": fake_client("claude", "no mention of anything relevant")})
    bot = ProspectingBot(RAW)
    records = bot.find_prospects(
        ICPFilter(categories=("Outdoor", "Beauty"), min_revenue=0, max_revenue=1e9),
        audit_bot=audit_bot, audit_top_n=1,
    )
    audited = [r for r in records if r.status == ProspectStatus.AUDIT_COMPLETE]
    assert len(audited) == 1
    assert audited[0].audit is not None
    assert audited[0].gap_note is not None
    not_audited = [r for r in records if r.status != ProspectStatus.AUDIT_COMPLETE]
    assert all(r.audit is None for r in not_audited)
