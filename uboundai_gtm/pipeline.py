"""Wires Prospecting -> Audit -> Outreach into one call, matching the GTM
pipeline: Competitive Monitoring and GEO Content are deliberately NOT part of
this chain — they run as their own independent, parallel tracks (see
`cli.py`'s `competitive` and `geo` commands).
"""
from __future__ import annotations

from dataclasses import dataclass

from .bots.audit_bot import AuditGenerationBot, AuditReport
from .bots.outreach_bot import OutreachBot, OutreachPackage
from .bots.prospecting_bot import ICPFilter, ProspectingBot, ProspectRecord
from .llm.registry import build_all_clients


@dataclass
class PipelineResult:
    prospect: ProspectRecord
    audit: AuditReport
    outreach: OutreachPackage


def run_pipeline(
    icp: ICPFilter | None = None,
    top_n: int = 3,
    audit_bot: AuditGenerationBot | None = None,
    outreach_bot: OutreachBot | None = None,
    prospecting_bot: ProspectingBot | None = None,
) -> list[PipelineResult]:
    """Prospecting finds and scores stores; the top `top_n` get a real audit;
    every audited prospect gets a personalized outreach package."""
    prospecting_bot = prospecting_bot or ProspectingBot()
    audit_bot = audit_bot or AuditGenerationBot(build_all_clients())
    outreach_bot = outreach_bot or OutreachBot()

    prospects = prospecting_bot.find_prospects(icp=icp, audit_bot=audit_bot, audit_top_n=top_n)

    results: list[PipelineResult] = []
    for prospect in prospects:
        if prospect.audit is None:
            continue
        outreach = outreach_bot.generate(prospect.audit, prospect.contact, prospect.product_category)
        results.append(PipelineResult(prospect=prospect, audit=prospect.audit, outreach=outreach))
    return results
