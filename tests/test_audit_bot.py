from __future__ import annotations

from uboundai_gtm.bots.audit_bot import AuditGenerationBot
from uboundai_gtm.llm.base import LLMRequestError, MissingAPIKeyError


def test_mentioned_brand_with_positive_sentiment_and_no_competitors(fake_client):
    bot = AuditGenerationBot({"claude": fake_client("claude", "Acme Outdoor is a great, highly recommended brand.")})
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")

    result = report.results[0]
    assert result.mentioned is True
    assert result.sentiment == "positive"
    assert report.mentioned_count == 1


def test_unmentioned_brand_is_flagged_in_note(fake_client):
    bot = AuditGenerationBot({"gemini": fake_client("gemini", "I'd recommend TrailKing for that.")})
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")

    result = report.results[0]
    assert result.mentioned is False
    assert "not mentioned" in result.note
    assert report.mentioned_count == 0


def test_share_of_voice_against_named_competitors(fake_client):
    text = "Acme Outdoor Acme Outdoor TrailKing"  # brand x2, competitor x1
    bot = AuditGenerationBot({"chatgpt": fake_client("chatgpt", text)})
    report = bot.run_audit(
        domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags",
        competitors=["TrailKing"],
    )
    assert report.results[0].share_of_voice == 2 / 3


def test_competitor_mentioned_more_prominently_note(fake_client):
    text = "TrailKing TrailKing TrailKing Acme Outdoor"  # competitor x3, brand x1
    bot = AuditGenerationBot({"perplexity": fake_client("perplexity", text)})
    report = bot.run_audit(
        domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags",
        competitors=["TrailKing"],
    )
    assert "TrailKing" in report.results[0].note


def test_hallucinated_price_is_flagged(fake_client):
    bot = AuditGenerationBot({"chatgpt": fake_client("chatgpt", "Acme Outdoor sells it for $59.")})
    report = bot.run_audit(
        domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags",
        known_facts={"price_usd": 39, "discontinued": False},
    )
    assert any("cites price $59" in issue and "actual price is $39" in issue for issue in report.flagged_issues)


def test_false_discontinued_claim_is_flagged(fake_client):
    bot = AuditGenerationBot({"perplexity": fake_client("perplexity", "That product line was discontinued last year.")})
    report = bot.run_audit(
        domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags",
        known_facts={"discontinued": False},
    )
    assert any("discontinued" in issue for issue in report.flagged_issues)


def test_correct_price_is_not_flagged(fake_client):
    bot = AuditGenerationBot({"chatgpt": fake_client("chatgpt", "Acme Outdoor sells it for $39.")})
    report = bot.run_audit(
        domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags",
        known_facts={"price_usd": 39},
    )
    assert report.flagged_issues == []


def test_missing_api_key_is_skipped_gracefully(fake_client):
    bot = AuditGenerationBot({"grok": fake_client("grok", MissingAPIKeyError("no key"))})
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")

    result = report.results[0]
    assert result.mentioned is False
    assert "no API key configured" in result.note


def test_request_error_is_caught_and_reported(fake_client):
    bot = AuditGenerationBot({"gemini": fake_client("gemini", LLMRequestError("timeout"))})
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")

    assert "request failed" in report.results[0].note


def test_overall_score_is_bounded_0_to_100(fake_client):
    bot = AuditGenerationBot({
        "claude": fake_client("claude", "Acme Outdoor is the best, most recommended brand."),
        "gemini": fake_client("gemini", "TrailKing is best."),
    })
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")
    assert 0 <= report.overall_score <= 100


def test_weakest_result_prefers_unmentioned_models(fake_client):
    bot = AuditGenerationBot({
        "claude": fake_client("claude", "Acme Outdoor Acme Outdoor"),
        "gemini": fake_client("gemini", "TrailKing only."),
    })
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")
    assert report.weakest_result.provider == "gemini"


def test_custom_queries_override_default_shopper_templates(fake_client):
    client = fake_client("gemini", "North Star Labs builds CyPhER for critical infrastructure.")
    bot = AuditGenerationBot({"gemini": client})
    custom_queries = [
        "What are the best network detection and response solutions for critical infrastructure?",
        "Which vendors offer signature-independent network sensing?",
    ]
    bot.run_audit(
        domain="northstarlabs.ai", brand_name="North Star Labs",
        product_category="network detection and response", queries=custom_queries,
    )
    assert client.calls == custom_queries
    assert "Where should I buy" not in "".join(client.calls)


def test_to_dict_round_trips_expected_keys(fake_client):
    bot = AuditGenerationBot({"claude": fake_client("claude", "Acme Outdoor is great.")})
    report = bot.run_audit(domain="acme.com", brand_name="Acme Outdoor", product_category="duffel bags")
    data = report.to_dict()
    assert set(data) == {
        "domain", "brand_name", "overall_score", "mentioned_count",
        "model_count", "avg_share_of_voice", "results", "flagged_issues",
    }
