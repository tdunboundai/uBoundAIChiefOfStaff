"""Bot 1 — Audit-Generation Bot.

Queries every configured LLM the way a shopper would, then scores what each
one says about the brand: whether it's mentioned, the sentiment, share of
voice against named competitors, and simple hallucination flags (wrong price,
falsely claimed as discontinued) checked against known facts.

This is the core product AND the free lead-magnet report the Outreach Bot
sends to prospects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ..llm.base import LLMAnswer, LLMClient, LLMRequestError, MissingAPIKeyError

POSITIVE_WORDS = {
    "best", "great", "excellent", "top", "recommend", "recommended",
    "love", "favorite", "trusted", "popular", "outstanding",
}
NEGATIVE_WORDS = {
    "avoid", "worse", "poor", "complaint", "discontinued", "unavailable",
    "out of stock", "overpriced", "scam", "unreliable",
}

DEFAULT_QUERY_TEMPLATES = [
    "Where should I buy {category}? Recommend a specific brand.",
    "What is the best brand for {category}?",
    "I'm shopping for {category} online — which brands do you recommend and why?",
]


@dataclass
class ModelResult:
    provider: str
    mentioned: bool
    sentiment: str  # "positive" | "neutral" | "negative"
    share_of_voice: float  # 0..1 across brand + named competitor mentions
    note: str = ""
    skipped: bool = False  # True when never actually queried (no key / request failed) —
    # `mentioned=False` here means "unknown", not "genuinely checked and absent"
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
                    "skipped": r.skipped,
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
    ) -> AuditReport:
        competitors = list(competitors)
        known_facts = known_facts or {}
        queries = list(queries) if queries else [
            t.format(category=product_category) for t in DEFAULT_QUERY_TEMPLATES
        ]

        results: list[ModelResult] = []
        flagged_issues: list[str] = []

        for provider, client in self.clients.items():
            try:
                answers = [client.ask(q) for q in queries]
            except MissingAPIKeyError:
                results.append(ModelResult(
                    provider=provider, mentioned=False, sentiment="neutral",
                    share_of_voice=0.0, note="no API key configured — skipped", skipped=True,
                ))
                continue
            except LLMRequestError as exc:
                results.append(ModelResult(
                    provider=provider, mentioned=False, sentiment="neutral",
                    share_of_voice=0.0, note=f"request failed: {exc}", skipped=True,
                ))
                continue

            combined_text = "\n".join(a.text for a in answers)
            mentioned = _mentions(combined_text, brand_name)
            sentiment = _sentiment(combined_text) if mentioned else "neutral"
            sov = _share_of_voice(combined_text, brand_name, competitors)
            model_issues = _hallucination_flags(provider, combined_text, known_facts)
            flagged_issues.extend(model_issues)

            note = ""
            if not mentioned:
                note = f"not mentioned by {provider}"
            elif competitors and sov < 0.5:
                leader = _leading_competitor(combined_text, competitors)
                if leader:
                    note = f"{leader} mentioned more prominently"
            if model_issues and not note:
                note = model_issues[0]

            results.append(ModelResult(
                provider=provider, mentioned=mentioned, sentiment=sentiment,
                share_of_voice=sov, note=note, raw_answers=answers,
            ))

        return AuditReport(domain=domain, brand_name=brand_name, results=results, flagged_issues=flagged_issues)


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
