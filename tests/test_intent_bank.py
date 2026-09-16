from __future__ import annotations

from uboundai_gtm.bots.audit_bot import AuditGenerationBot
from uboundai_gtm.bots.intent_bank import DEFAULT_INTENT_BANK, get_intent_bank


def test_cosmetics_bank_has_fifteen_distinct_intents():
    bank = get_intent_bank("cosmetics")
    assert len(bank) == 15
    labels = [item["intent"] for item in bank]
    assert len(labels) == len(set(labels)), "intent labels must be unique"


def test_cosmetics_bank_lookup_is_case_insensitive():
    assert get_intent_bank("Cosmetics") == get_intent_bank("cosmetics")
    assert get_intent_bank("  cosmetics  ") == get_intent_bank("cosmetics")


def test_unknown_category_falls_back_to_default_bank():
    assert get_intent_bank("underwater basket weaving") == DEFAULT_INTENT_BANK


def test_every_query_template_uses_the_category_placeholder():
    for item in get_intent_bank("cosmetics"):
        assert "{category}" in item["query"], item["intent"]


def test_run_audit_fires_one_call_per_intent_bank_entry(fake_client):
    client = fake_client("gemini", "e.l.f. Cosmetics is a great, popular brand.")
    bot = AuditGenerationBot({"gemini": client})
    bank = get_intent_bank("cosmetics")

    bot.run_audit(
        domain="elfcosmetics.com", brand_name="e.l.f. Cosmetics",
        product_category="cosmetics", intent_bank=bank,
    )

    assert len(client.calls) == 15
    assert all("cosmetics" in q for q in client.calls)
    assert len(set(client.calls)) == 15, "every intent should produce a distinct query"


def test_per_intent_breakdown_is_exposed_in_report(fake_client):
    client = fake_client("gemini", "e.l.f. Cosmetics is a great, popular brand.")
    bot = AuditGenerationBot({"gemini": client})
    report = bot.run_audit(
        domain="elfcosmetics.com", brand_name="e.l.f. Cosmetics",
        product_category="cosmetics", intent_bank=get_intent_bank("cosmetics"),
    )

    result = report.results[0]
    assert len(result.intent_results) == 15
    intents_seen = {ir.intent for ir in result.intent_results}
    assert "best_overall" in intents_seen
    assert "cruelty_free" in intents_seen

    data = report.to_dict()
    breakdown = data["results"][0]["intent_breakdown"]
    assert len(breakdown) == 15
    assert breakdown[0].keys() == {"intent", "query", "mentioned", "sentiment", "share_of_voice"}


def test_brand_can_win_one_intent_and_lose_another(fake_client):
    """A single merged-blob analysis can't see this; per-intent tracking can."""
    responses = {
        "What is the best brand for cosmetics?": "e.l.f. Cosmetics is a top pick.",
        "What's the most affordable drugstore cosmetics brand?": "ColourPop is the most affordable.",
    }

    class ScriptedClient:
        provider = "gemini"

        def __init__(self):
            self.calls = []

        def ask(self, query):
            from uboundai_gtm.llm.base import LLMAnswer
            self.calls.append(query)
            return LLMAnswer(provider="gemini", model="fake", query=query, text=responses[query])

    bank = [
        {"intent": "best_overall", "query": "What is the best brand for {category}?"},
        {"intent": "budget_friendly", "query": "What's the most affordable drugstore {category} brand?"},
    ]
    bot = AuditGenerationBot({"gemini": ScriptedClient()})
    report = bot.run_audit(
        domain="elfcosmetics.com", brand_name="e.l.f. Cosmetics", product_category="cosmetics",
        competitors=["ColourPop"], intent_bank=bank,
    )

    by_intent = {ir.intent: ir for ir in report.results[0].intent_results}
    assert by_intent["best_overall"].mentioned is True
    assert by_intent["budget_friendly"].mentioned is False


def test_partial_failure_partway_through_bank_keeps_completed_intents(fake_client):
    """Regression test: a real 15-query run against a free-tier API failed
    partway through (a transient 503 after retries were exhausted), and the
    old all-or-nothing behavior threw away every intent that had already
    succeeded. It should keep them and mark the result as audited-but-partial,
    not skipped."""
    from uboundai_gtm.llm.base import LLMAnswer, LLMClient, LLMRequestError

    class FlakyClient(LLMClient):
        provider = "gemini"

        def __init__(self):
            super().__init__(api_key="fake")
            self.calls = 0

        def ask(self, query):
            self.calls += 1
            if self.calls == 3:
                raise LLMRequestError("503 after retries")
            return LLMAnswer(provider="gemini", model="fake", query=query, text="e.l.f. Cosmetics is great.")

    bank = get_intent_bank("cosmetics")  # 15 entries
    client = FlakyClient()
    bot = AuditGenerationBot({"gemini": client})
    report = bot.run_audit(
        domain="elfcosmetics.com", brand_name="e.l.f. Cosmetics",
        product_category="cosmetics", intent_bank=bank,
    )

    result = report.results[0]
    assert result.skipped is False, "2 successful intents is real data, not zero"
    assert len(result.intent_results) == 2
    assert "stopped after 2/15 intents" in result.coverage_note
    assert "stopped after" not in result.note, "technical/diagnostic text must never land in the marketing-safe note"
    assert result.mentioned is True
    assert client.calls == 3  # stopped immediately on the failure, didn't skip ahead


def test_duplicate_hallucination_flags_across_intents_are_deduped(fake_client):
    client = fake_client("chatgpt", "e.l.f. Cosmetics sells it for $59.")
    bot = AuditGenerationBot({"chatgpt": client})
    report = bot.run_audit(
        domain="elfcosmetics.com", brand_name="e.l.f. Cosmetics", product_category="cosmetics",
        known_facts={"price_usd": 39}, intent_bank=get_intent_bank("cosmetics"),
    )
    price_flags = [issue for issue in report.flagged_issues if "cites price $59" in issue]
    assert len(price_flags) == 1
