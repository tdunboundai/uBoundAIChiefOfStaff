"""Command-line entry points for all 5 bots and the combined pipeline.

Every subcommand prints JSON to stdout. Run with
`python -m uboundai_gtm.cli <command> ...` or via the `uboundai-gtm` console
script installed by pyproject.toml.
"""
from __future__ import annotations

import argparse
import json
import sys

from .bots.audit_bot import AuditGenerationBot
from .bots.competitive_bot import CompetitiveMonitoringBot
from .bots.geo_content_bot import ContentChannel, ContentStatus, GEOContentBot
from .bots.intent_bank import get_intent_bank
from .bots.outreach_bot import OutreachBot
from .bots.prospecting_bot import ICPFilter, ProspectingBot
from .data import load_prospects
from .llm.registry import build_all_clients
from .pipeline import run_pipeline
from .scraping import SEED_DOMAINS, discover_from_seed_list, discover_from_seed_list_any_platform


def _emit(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def _lookup_prospect(prospect_id: str) -> dict:
    prospects = {p["id"]: p for p in load_prospects()}
    if prospect_id not in prospects:
        sys.exit(f"Unknown prospect id '{prospect_id}'. Known: {', '.join(prospects)}")
    return prospects[prospect_id]


def cmd_audit(args: argparse.Namespace) -> None:
    bot = AuditGenerationBot(build_all_clients())

    if args.prospect:
        p = _lookup_prospect(args.prospect)
        report = bot.run_audit(
            domain=p["domain"], brand_name=p["brand_name"], product_category=p["product_category"],
            competitors=p["competitors"], known_facts=p["known_facts"],
            intent_bank=get_intent_bank(p["product_category"]),
        )
    else:
        if not (args.domain and args.brand and args.category):
            sys.exit("--domain, --brand and --category are required when not using --prospect")
        known_facts = {"price_usd": args.price} if args.price is not None else {}
        # --query is an explicit override (e.g. B2B evaluation phrasing) and always
        # wins; otherwise auto-pick a curated intent bank for the category, falling
        # back to the 3-question generic default when none exists for it yet.
        if args.query:
            report = bot.run_audit(
                domain=args.domain, brand_name=args.brand, product_category=args.category,
                competitors=args.competitor or [], known_facts=known_facts, queries=args.query,
            )
        else:
            report = bot.run_audit(
                domain=args.domain, brand_name=args.brand, product_category=args.category,
                competitors=args.competitor or [], known_facts=known_facts,
                intent_bank=get_intent_bank(args.category),
            )
    _emit(report.to_dict())


def cmd_prospect(args: argparse.Namespace) -> None:
    icp = ICPFilter(
        categories=tuple(args.category) if args.category else ICPFilter().categories,
        min_revenue=args.min_revenue, max_revenue=args.max_revenue,
    )
    audit_bot = AuditGenerationBot(build_all_clients()) if args.audit_top else None
    records = ProspectingBot().find_prospects(icp=icp, audit_bot=audit_bot, audit_top_n=args.audit_top)
    _emit([r.to_dict() for r in records])


def cmd_outreach(args: argparse.Namespace) -> None:
    p = _lookup_prospect(args.prospect)
    clients = build_all_clients()
    report = AuditGenerationBot(clients).run_audit(
        domain=p["domain"], brand_name=p["brand_name"], product_category=p["product_category"],
        competitors=p["competitors"], known_facts=p["known_facts"],
        intent_bank=get_intent_bank(p["product_category"]),
    )
    copy_client = clients["claude"] if args.llm_copy else None
    package = OutreachBot(copy_client=copy_client).generate(report, p["contact"], p["product_category"])
    _emit({"audit": report.to_dict(), "outreach": package.to_dict()})


def cmd_competitive(args: argparse.Namespace) -> None:
    report = CompetitiveMonitoringBot().scan(alert_window_days=args.window)
    _emit(report.to_dict())


def cmd_geo(args: argparse.Namespace) -> None:
    """Seeds a demo content board (no persistence layer yet — a real
    deployment would back this with a DB/CMS) and optionally checks whether
    one published card is already being cited."""
    bot = GEOContentBot()
    bot.add_card(
        "Guide: how AI shopping assistants pick which brand to recommend",
        ContentChannel.STANDARD, ContentStatus.DRAFT,
    )
    bot.add_card(
        "Thread: we audited 50 Shopify brands' AI visibility — full results",
        ContentChannel.X_GROK, ContentStatus.SCHEDULED,
    )
    bot.add_card(
        "Docs: UnboundAI methodology — how we query 5 LLMs",
        ContentChannel.STANDARD, ContentStatus.SCHEDULED,
    )
    bot.add_card(
        "Comparison: AEO vs. GEO vs. traditional SEO",
        ContentChannel.STANDARD, ContentStatus.PUBLISHED,
    )
    bot.add_card(
        "X thread: which AI assistants hallucinate prices most",
        ContentChannel.X_GROK, ContentStatus.PUBLISHED,
    )
    flagship = bot.add_card(
        "Blog: State of AI Shopping Search 2026",
        ContentChannel.STANDARD, ContentStatus.PUBLISHED,
    )

    if args.check_citations:
        bot.clients = build_all_clients()
        bot.check_citation(
            flagship.id, "What's a good resource on the state of AI shopping search?", "UnboundAI"
        )

    _emit(bot.board())


def cmd_scrape(args: argparse.Namespace) -> None:
    """Bot 2 (live): discovers real stores from the built-in demo seed list
    (swap in your own list once you have one — same shape as
    `scraping.seed_domains.SEED_DOMAINS`). Needs real internet access; any
    domain it can't reach is skipped, not fatal.

    Default mode requires Shopify (fingerprint + `/products.json`) and
    rejects anything else — that's the reliable, high-confidence path.
    `--any-platform` accepts any domain, falling back to schema.org JSON-LD
    or Open Graph product tags when it isn't Shopify; lower-confidence, and
    the result's `platform` field says which tier actually matched."""
    if args.any_platform:
        prospects, errors = discover_from_seed_list_any_platform(SEED_DOMAINS)
    else:
        prospects, errors = discover_from_seed_list(SEED_DOMAINS)

    if args.score and prospects:
        records = ProspectingBot(prospects).find_prospects()
        _emit({"prospects": [r.to_dict() for r in records], "errors": errors})
    else:
        _emit({"prospects": prospects, "errors": errors})


def cmd_pipeline(args: argparse.Namespace) -> None:
    icp = ICPFilter(
        categories=tuple(args.category) if args.category else ICPFilter().categories,
        min_revenue=args.min_revenue, max_revenue=args.max_revenue,
    )
    results = run_pipeline(icp=icp, top_n=args.top_n)
    _emit([
        {"prospect": r.prospect.to_dict(), "audit": r.audit.to_dict(), "outreach": r.outreach.to_dict()}
        for r in results
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uboundai-gtm",
        description="UnboundAI GTM bots: prospecting, audit, outreach, competitive monitoring, GEO content.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="Bot 1: run an AI visibility audit")
    p_audit.add_argument("--prospect", help="Use a mock prospect id (see `prospect` command output)")
    p_audit.add_argument("--domain")
    p_audit.add_argument("--brand")
    p_audit.add_argument("--category")
    p_audit.add_argument("--competitor", action="append")
    p_audit.add_argument("--price", type=float)
    p_audit.add_argument(
        "--query", action="append",
        help="Override the default shopper-style query templates (repeatable) — use "
             "B2B evaluation phrasing for non-retail brands, e.g. "
             "--query \"What are the best network detection tools for critical infrastructure?\"",
    )
    p_audit.set_defaults(func=cmd_audit)

    p_prospect = sub.add_parser("prospect", help="Bot 2: find and score prospects")
    p_prospect.add_argument("--category", action="append")
    p_prospect.add_argument("--min-revenue", type=float, default=ICPFilter().min_revenue)
    p_prospect.add_argument("--max-revenue", type=float, default=ICPFilter().max_revenue)
    p_prospect.add_argument(
        "--audit-top", type=int, default=0, help="Auto-run the Audit Bot on the top N prospects"
    )
    p_prospect.set_defaults(func=cmd_prospect)

    p_outreach = sub.add_parser("outreach", help="Bot 3: generate a personalized pitch for one prospect")
    p_outreach.add_argument("--prospect", required=True)
    p_outreach.add_argument(
        "--llm-copy", action="store_true",
        help="Use Claude to write the email body (falls back to a template on any failure)",
    )
    p_outreach.set_defaults(func=cmd_outreach)

    p_competitive = sub.add_parser("competitive", help="Bot 4: scan tracked competitors")
    p_competitive.add_argument("--window", type=int, default=14, help="Alert window in days")
    p_competitive.set_defaults(func=cmd_competitive)

    p_geo = sub.add_parser("geo", help="Bot 5: GEO content board (demo data)")
    p_geo.add_argument(
        "--check-citations", action="store_true",
        help="Query all 5 LLMs to check if a published card is already cited",
    )
    p_geo.set_defaults(func=cmd_geo)

    p_scrape = sub.add_parser(
        "scrape", help="Bot 2 (live): discover real Shopify stores from the demo seed list"
    )
    p_scrape.add_argument("--score", action="store_true", help="Run ICP scoring on the scraped results")
    p_scrape.add_argument(
        "--any-platform", action="store_true",
        help="Don't require Shopify; fall back to schema.org JSON-LD / Open Graph product tags",
    )
    p_scrape.set_defaults(func=cmd_scrape)

    p_pipeline = sub.add_parser("pipeline", help="Prospecting -> Audit -> Outreach end to end")
    p_pipeline.add_argument("--category", action="append")
    p_pipeline.add_argument("--min-revenue", type=float, default=ICPFilter().min_revenue)
    p_pipeline.add_argument("--max-revenue", type=float, default=ICPFilter().max_revenue)
    p_pipeline.add_argument("--top-n", type=int, default=3)
    p_pipeline.set_defaults(func=cmd_pipeline)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
