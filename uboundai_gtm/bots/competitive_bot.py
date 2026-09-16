"""Bot 4 — Competitive & Category-Monitoring Bot.

Tracks named competitors (LLMrefs, Shop Mentions, FSEO, Semrush's LLM add-on,
Lexsis) and surfaces recent pricing/positioning/changelog moves as alerts, so
messaging stays differentiated instead of converging with theirs.

Reads from `uboundai_gtm.data.load_competitors()` by default — a mock
dataset today; swap that loader for real scraping of App Store listings,
changelogs and pricing pages without touching the alerting logic here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..data import load_competitors

OUR_MODELS_TRACKED = 5  # Gemini, ChatGPT, Perplexity, Grok, Claude


@dataclass
class CompetitorRow:
    name: str
    pricing: str
    positioning: str
    app_store_rating: float | None
    app_store_reviews: int
    shopify_native: bool
    models_tracked: int
    last_change_note: str | None
    last_change_days_ago: int | None

    def to_dict(self) -> dict:
        if self.app_store_rating:
            app_store = f"{self.app_store_rating}★ ({self.app_store_reviews})"
        elif not self.shopify_native:
            app_store = "n/a — not Shopify-native"
        else:
            app_store = "n/a"

        last_change = (
            "No change" if self.last_change_note is None
            else f"{self.last_change_note} — {self.last_change_days_ago}d ago"
        )
        return {
            "name": self.name,
            "pricing": self.pricing,
            "positioning": self.positioning,
            "app_store": app_store,
            "last_change": last_change,
        }


@dataclass
class CompetitiveReport:
    rows: list[CompetitorRow]
    alerts: list[str]

    def to_dict(self) -> dict:
        return {"rows": [r.to_dict() for r in self.rows], "alerts": self.alerts}


class CompetitiveMonitoringBot:
    def __init__(self, competitors: list[dict] | None = None):
        self._raw = list(competitors) if competitors is not None else load_competitors()

    def scan(self, reference_date: date | None = None, alert_window_days: int = 14) -> CompetitiveReport:
        reference_date = reference_date or date.today()
        rows: list[CompetitorRow] = []
        alerts: list[str] = []

        for c in self._raw:
            changelog = sorted(c.get("changelog", []), key=lambda e: e["date"], reverse=True)
            note, days_ago = None, None
            if changelog:
                latest = changelog[0]
                entry_date = datetime.strptime(latest["date"], "%Y-%m-%d").date()
                days_ago = (reference_date - entry_date).days
                note = latest["note"]

            row = CompetitorRow(
                name=c["name"],
                pricing=c["pricing"],
                positioning=c["positioning"],
                app_store_rating=c.get("app_store_rating"),
                app_store_reviews=c.get("app_store_reviews", 0),
                shopify_native=c.get("shopify_native", True),
                models_tracked=c.get("models_tracked", 0),
                last_change_note=note,
                last_change_days_ago=days_ago,
            )
            rows.append(row)

            if days_ago is not None and 0 <= days_ago <= alert_window_days:
                first_word, _, rest = note.partition(" ")
                alert = f"New: {c['name']} {first_word[0].lower()}{first_word[1:]}{' ' + rest if rest else ''} ({days_ago}d ago)."
                if row.models_tracked >= OUR_MODELS_TRACKED - 2:
                    alert += (
                        f" They track {row.models_tracked} models vs. our {OUR_MODELS_TRACKED} — "
                        "lead with multi-model breadth in messaging."
                    )
                alerts.append(alert)

        return CompetitiveReport(rows=rows, alerts=alerts)
