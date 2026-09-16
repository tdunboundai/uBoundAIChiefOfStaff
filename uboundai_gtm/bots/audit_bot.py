"""Bot 1 — Audit-Generation Bot.

Queries every configured LLM with a bank of distinct shopper-intent queries
(not one repeated "recommend a brand" question), scoring each intent
separately: whether the brand is mentioned, sentiment, share of voice
against named competitors, and hallucination flags (wrong price, falsely
claimed as discontinued) checked against known facts. Per-model results are
an aggregate across intents, but the per-intent breakdown survives in
`ModelResult.intent_results` — a brand can win on one intent and lose on
another, which a single merged query can't distinguish.

This is the core product AND the free lead-magnet report the Outreach Bot
sends to prospects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ..llm.base import LLMAnswer, LLMClient, LLMRequestError, MissingAPIKeyError
from .intent_bank import DEFAULT_INTENT_BANK

POSITIVE_WORDS = {
    "best", "great", "excellent", "top", "recommend", "recommended",
    "love", "favorite", "trusted", "popular", "outstanding",
}
NEGATIVE_WORDS = {
    "avoid", "worse", "poor", "complaint", "discontinued", "unavailable",
    "out of stock", "overpriced", "scam", "unreliable",
}

# Backward-compatible alias — some callers/tests still import this name.
DEFAULT_QUERY_TEMPLATES = [item["query"] for item in DEFAULT_INTENT_BANK]


@dataclass
class IntentResult:
    """One query's result, before aggregation into a ModelResult."""
    intent: str
    query: str
    mentioned: bool
    sentiment: str
    share_of_voice: float
    text: str = ""  # raw response text; kept for aggregation (e.g. finding the
    # leading competitor across all intents), not surfaced in to_dict output

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "query": self.query,
            "mentioned": self.mentioned,
            "sentiment": self.sentiment,
            "share_of_voice": round(self.share_of_voice, 2),
        }


@dataclass
class ModelResult:
    provider: str
    mentioned: bool
    sentiment: str  # "positive" | "neutral" | "negative"
    share_of_voice: float  # 0..1 across brand + named competitor mentions
    note: str = ""  # marketing-safe finding only, e.g. "NYX mentioned more prominently" —
    # this is the ONLY field the Outreach Bot may quote in generated copy.
    coverage_note: str = ""  # technical/diagnostic only (missing key, request error,
    # partial completion) — may contain raw provider error text; internal/report use only,
    # never surfaced in outreach copy.
    skipped: bool = False  # True when never actually queried (no key / request failed) —
    # `mentioned=False` here means "unknown", not "genuinely checked and absent"
    intent_results: list[IntentResult] = field(default_factory=list)
    raw_answers: list[LLMAnswer] = field(default_factory=list)


@dataclass
class AuditReport:
    domain: str
    brand_name: str
    results: list[ModelResult]
    flagged_issues: list[str]

    @property
    def audited_results(self) -> list[ModelResult]:
        """Results from models that were actually queried. Every score and the
        Outreach Bot's hook are built from this, not `results` — a model with
        no API key configured is unaudited, not evidence of a visibility gap."""
        return [r for r in self.results if not r.skipped]

    @property
    def mentioned_count(self) -> int:
        return sum(1 for r in self.results if r.mentioned)

    @property
    def avg_share_of_voice(self) -> float:
        audited = self.audited_results
        if not audited:
            return 0.0
        return sum(r.share_of_voice for r in audited) / len(audited)

    @property
    def overall_score(self) -> int:
        """0-100 composite of mention rate, sentiment, and share of voice,
        computed only over audited models — an unaudited model is missing
        data, not a negative signal."""
        audited = self.audited_results
        if not audited:
            return 0
        sentiment_points = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
        mention_rate = self.mentioned_count / len(audited)
        sentiment_score = sum(sentiment_points[r.sentiment] for r in audited) / len(audited)
        score = 100 * (0.4 * mention_rate + 0.3 * sentiment_score + 0.3 * self.avg_share_of_voice)
        return round(score)

    @property
    def weakest_result(self) -> ModelResult | None:
        """The audited model with the biggest opportunity — lowest share of
        voice, unmentioned models first. Used by the Outreach Bot as the
        hook; never an unaudited (skipped) model."""
        audited = self.audited_results
        if not audited:
            return None
        return min(audited, key=lambda r: (r.mentioned, r.share_of_voice))

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "brand_name": self.brand_name,
            "overall_score": self.overall_score,
            "mentioned_count": self.mentioned_count,
            "audited_count": len(self.audited_results),
            "model_count": len(self.results),
            "avg_share_of_voice": round(self.avg_share_of_voice, 2),
            "results": [
                {
                    "provider": r.provider,
                    "mentioned": r.mentioned,
                    "sentiment": r.sentiment,
                    "share_of_voice": round(r.share_of_voice, 2),
                    "note": r.note,
                    "coverage_note": r.coverage_note,
                    "skipped": r.skipped,
                    "intent_breakdown": [ir.to_dict() for ir in r.intent_results],
                }
                for r in self.results
            ],
            "flagged_issues": self.flagged_issues,
        }


class AuditGenerationBot:
    def __init__(self, clients: dict[str, LLMClient]):
        self.clients = clients

    def run_audit(
        self,
        domain: str,
        brand_name: str,
        product_category: str,
        competitors: Iterable[str] = (),
        known_facts: dict | None = None,
        queries: Iterable[str] | None = None,
        intent_bank: Iterable[dict] | None = None,
    ) -> AuditReport:
        """`intent_bank` (a list of `{"intent", "query"}`, see `intent_bank.py`)
        takes precedence when given. `queries` (plain strings, e.g. from the
        CLI's `--query`) still works for one-off overrides — each becomes its
        own anonymous intent. With neither, falls back to the 3-question
        generic default."""
        competitors = list(competitors)
        known_facts = known_facts or {}

        if intent_bank:
            intents = [
                {"intent": item["intent"], "query": item["query"].format(category=product_category)}
                for item in intent_bank
            ]
        elif queries:
            intents = [{"intent": f"custom_{i + 1}", "query": q} for i, q in enumerate(queries)]
        else:
            intents = [
                {"intent": f"default_{i + 1}", "query": t.format(category=product_category)}
                for i, t in enumerate(DEFAULT_QUERY_TEMPLATES)
            ]

        results: list[ModelResult] = []
        flagged_issues: list[str] = []

        for provider, client in self.clients.items():
            intent_results: list[IntentResult] = []
            error_note: str | None = None

            for item in intents:
                try:
                    answer = client.ask(item["query"])
                except MissingAPIKeyError:
                    error_note = "no API key configured — skipped"
                    break
                except LLMRequestError as exc:
                    # A real provider under load can fail partway through a 15-query
                    # bank; keep whatever intents already succeeded instead of
                    # throwing away a mostly-complete audit over one bad call.
                    error_note = f"stopped after {len(intent_results)}/{len(intents)} intents: {exc}"
                    break

                text = answer.text
                mentioned = _mentions(text, brand_name)
                sentiment = _sentiment(text) if mentioned else "neutral"
                sov = _share_of_voice(text, brand_name, competitors)
                flagged_issues.extend(_hallucination_flags(provider, text, known_facts))
                intent_results.append(IntentResult(
                    intent=item["intent"], query=item["query"], mentioned=mentioned,
                    sentiment=sentiment, share_of_voice=sov, text=text,
                ))

            if not intent_results:
                results.append(ModelResult(
                    provider=provider, mentioned=False, sentiment="neutral",
                    share_of_voice=0.0, note="", coverage_note=error_note or "no data", skipped=True,
                ))
                continue

            model_result = _aggregate_model_result(provider, intent_results, competitors)
            if error_note:
                # Partial coverage, not zero — still real, audited data. This goes in
                # coverage_note, NEVER note: note is the only field the Outreach Bot
                # is allowed to quote, and raw provider error text (even redacted of
                # secrets) has no business in customer-facing copy.
                model_result.coverage_note = error_note
            results.append(model_result)

        # A hallucination repeated across several query intents shouldn't show
        # up as several identical entries.
        flagged_issues = list(dict.fromkeys(flagged_issues))

        return AuditReport(domain=domain, brand_name=brand_name, results=results, flagged_issues=flagged_issues)


def _aggregate_model_result(provider: str, intent_results: list[IntentResult], competitors: list[str]) -> ModelResult:
    mentioned = any(ir.mentioned for ir in intent_results)
    sentiment_points = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
    avg_sentiment_score = sum(sentiment_points[ir.sentiment] for ir in intent_results) / len(intent_results)
    if avg_sentiment_score >= 0.66:
        sentiment = "positive"
    elif avg_sentiment_score <= 0.33:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    share_of_voice = sum(ir.share_of_voice for ir in intent_results) / len(intent_results)
    combined_text = "\n".join(ir.text for ir in intent_results)

    note = ""
    if not mentioned:
        note = f"not mentioned by {provider}"
    elif competitors and share_of_voice < 0.5:
        leader = _leading_competitor(combined_text, competitors)
        if leader:
            note = f"{leader} mentioned more prominently"

    return ModelResult(
        provider=provider, mentioned=mentioned, sentiment=sentiment,
        share_of_voice=share_of_voice, note=note, intent_results=intent_results,
    )


def _mentions(text: str, name: str) -> bool:
    return bool(re.search(re.escape(name), text, re.IGNORECASE))


def _sentiment(text: str) -> str:
    lower = text.lower()
    pos = sum(lower.count(w) for w in POSITIVE_WORDS)
    neg = sum(lower.count(w) for w in NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _share_of_voice(text: str, brand_name: str, competitors: list[str]) -> float:
    lower = text.lower()
    brand_hits = lower.count(brand_name.lower())
    competitor_hits = sum(lower.count(c.lower()) for c in competitors)
    total = brand_hits + competitor_hits
    if total == 0:
        return 0.0
    return brand_hits / total


def _leading_competitor(text: str, competitors: list[str]) -> str | None:
    lower = text.lower()
    counts = {c: lower.count(c.lower()) for c in competitors}
    counts = {c: n for c, n in counts.items() if n > 0}
    if not counts:
        return None
    return max(counts, key=counts.get)


_PRICE_RE = re.compile(r"\$\s?(\d+(?:\.\d{2})?)")
_DISCONTINUED_RE = re.compile(
    r"\b(discontinued|no longer (available|sold|made)|out of production)\b", re.IGNORECASE
)


def _hallucination_flags(provider: str, text: str, known_facts: dict) -> list[str]:
    """Heuristic v1: regex pattern-matching against known facts. Good enough to
    catch obvious price/availability errors; an LLM-as-judge pass is the
    natural upgrade once this is validated against real audits."""
    issues: list[str] = []

    actual_price = known_facts.get("price_usd")
    if actual_price is not None:
        for match in _PRICE_RE.finditer(text):
            cited = float(match.group(1))
            if abs(cited - float(actual_price)) >= 1:
                issues.append(f"{provider}: cites price ${cited:g}; actual price is ${actual_price:g}.")
                break

    if known_facts.get("discontinued") is False and _DISCONTINUED_RE.search(text):
        issues.append(f"{provider}: claims the product is discontinued — this is false.")

    return issues
