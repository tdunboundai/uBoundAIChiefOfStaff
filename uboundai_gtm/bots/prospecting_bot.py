"""Bot 2 — Prospecting Bot.

Scores Shopify stores against an ICP filter and, for the top-ranked
candidates, automatically calls the Audit-Generation Bot so the visibility
gap on the lead list is real, not guessed.

`ProspectingBot` reads from `uboundai_gtm.data.load_prospects()` by default,
which is a mock dataset today — swap that loader for a real firmographic
source (BuiltWith, SimilarWeb, Shopify Partner API, ...) without touching
this bot's scoring or audit-triggering logic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from ..data import load_prospects
from .audit_bot import AuditGenerationBot, AuditReport

DEFAULT_ICP_CATEGORIES = ("Outdoor", "Apparel", "Beauty")
SWEET_SPOT_REVENUE = 3_000_000  # v1 heuristic center; see _score()


class ProspectStatus(str, Enum):
    NEW = "New"
    AUDIT_QUEUED = "Audit Queued"
    AUDIT_COMPLETE = "Audit Complete"
    CONTACTED = "Contacted"
    SKIPPED = "Skipped"


@dataclass(frozen=True)
class ICPFilter:
    categories: tuple[str, ...] = DEFAULT_ICP_CATEGORIES
    min_revenue: float = 1_000_000
    max_revenue: float = 20_000_000


@dataclass
class ProspectRecord:
    id: str
    store: str
    domain: str
    brand_name: str
    category: str
    monthly_revenue_est: float
    competitors: list[str]
    product_category: str
    known_facts: dict
    contact: dict
    icp_score: int
    status: ProspectStatus = ProspectStatus.NEW
    audit: AuditReport | None = None
    gap_note: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "store": self.store,
            "domain": self.domain,
            "category": self.category,
            "monthly_revenue_est": self.monthly_revenue_est,
            "icp_score": self.icp_score,
            "status": self.status.value,
            "gap_note": self.gap_note or "not yet audited",
        }


class ProspectingBot:
    def __init__(self, prospects: Iterable[dict] | None = None):
        self._raw = list(prospects) if prospects is not None else load_prospects()

    def find_prospects(
        self,
        icp: ICPFilter | None = None,
        audit_bot: AuditGenerationBot | None = None,
        audit_top_n: int = 0,
    ) -> list[ProspectRecord]:
        icp = icp or ICPFilter()
        candidates = [
            p for p in self._raw
            if p["category"] in icp.categories
            and icp.min_revenue <= p["monthly_revenue_est"] <= icp.max_revenue
        ]

        records = [
            ProspectRecord(
                id=p["id"], store=p["store"], domain=p["domain"], brand_name=p["brand_name"],
                category=p["category"], monthly_revenue_est=p["monthly_revenue_est"],
                competitors=list(p["competitors"]), product_category=p["product_category"],
                known_facts=dict(p["known_facts"]), contact=dict(p["contact"]),
                icp_score=_score(p["monthly_revenue_est"]),
            )
            for p in candidates
        ]
        records.sort(key=lambda r: r.icp_score, reverse=True)

        if audit_bot and audit_top_n:
            for record in records[:audit_top_n]:
                record.status = ProspectStatus.AUDIT_QUEUED
                report = audit_bot.run_audit(
                    domain=record.domain,
                    brand_name=record.brand_name,
                    product_category=record.product_category,
                    competitors=record.competitors,
                    known_facts=record.known_facts,
                )
                record.audit = report
                record.status = ProspectStatus.AUDIT_COMPLETE
                record.gap_note = _gap_note(report)

        return records


def _score(revenue: float) -> int:
    """v1 heuristic: rewards revenue near a $3M sweet spot on a log scale.
    Category weight is flat here because ICP filtering already enforces a
    match; replace with real firmographic/ad-spend/tech-stack signals once
    a live data source is wired in."""
    fit = max(0.0, 1 - abs(math.log10(revenue) - math.log10(SWEET_SPOT_REVENUE)))
    return round(60 * fit + 40)


def _gap_note(report: AuditReport) -> str:
    if report.mentioned_count == 0:
        return f"0 of {len(report.results)} models mention the brand"
    weakest = report.weakest_result
    if weakest and weakest.note:
        return weakest.note
    return "no visibility gap detected"
