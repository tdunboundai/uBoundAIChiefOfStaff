"""Curated shopper-intent query banks for the Audit-Generation Bot.

The bare default (3 templates, all variations of "recommend a brand") only
samples one intent. A real shopper funnel has many distinct intents — price,
quality, trust, use-case — and a brand can win on one and lose on another,
which a single merged "recommend a brand" query can't see.

Each entry is `{"intent": <short stable label>, "query": <template>}`; the
query template takes `{category}` (filled in at call time with whatever
`product_category` the audit is run with). Entries are deliberately generic
to the category, not to any one brand, so the same bank works for auditing
any brand that sells in that category.
"""
from __future__ import annotations

DEFAULT_INTENT_BANK: list[dict] = [
    {"intent": "best_overall", "query": "What is the best brand for {category}?"},
    {"intent": "where_to_buy", "query": "Where should I buy {category}? Recommend a specific brand."},
    {"intent": "shopping_recommendation", "query": "I'm shopping for {category} online — which brands do you recommend and why?"},
]

# Add a category key here as coverage grows; anything not listed falls back
# to DEFAULT_INTENT_BANK via get_intent_bank().
CATEGORY_INTENT_BANKS: dict[str, list[dict]] = {
    "cosmetics": [
        {"intent": "best_overall", "query": "What is the best brand for {category}?"},
        {"intent": "where_to_buy", "query": "Where should I buy {category} online? Recommend a specific brand."},
        {"intent": "shopping_recommendation", "query": "I'm shopping for {category} online — which brands do you recommend and why?"},
        {"intent": "budget_friendly", "query": "What's the most affordable drugstore {category} brand?"},
        {"intent": "premium_quality", "query": "What's the best high-quality, premium {category} brand?"},
        {"intent": "trusted_by_experts", "query": "Which {category} brands are most trusted by dermatologists and makeup artists?"},
        {"intent": "cruelty_free", "query": "What are the best cruelty-free {category} brands?"},
        {"intent": "value_for_money", "query": "Which {category} brand offers the best value for money?"},
        {"intent": "beginner_friendly", "query": "What's a good {category} brand for makeup beginners?"},
        {"intent": "trending", "query": "What {category} brands are trending right now on social media?"},
        {"intent": "near_me_affordable", "query": "Where can I buy affordable {category} near me or online?"},
        {"intent": "sensitive_skin", "query": "What's the best {category} brand for sensitive or acne-prone skin?"},
        {"intent": "long_lasting", "query": "Which {category} brand has the most long-lasting, smudge-proof formulas?"},
        {"intent": "gift_recommendation", "query": "What {category} brand would make a good gift set?"},
        {"intent": "clean_ingredients", "query": "What are the best clean or non-toxic {category} brands?"},
    ],
}


def get_intent_bank(category: str) -> list[dict]:
    return CATEGORY_INTENT_BANKS.get(category.strip().lower(), DEFAULT_INTENT_BANK)
