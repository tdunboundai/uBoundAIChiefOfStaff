from __future__ import annotations

from datetime import date

from uboundai_gtm.bots.competitive_bot import CompetitiveMonitoringBot

REFERENCE = date(2026, 9, 16)

COMPETITORS = [
    {
        "name": "RecentMover", "pricing": "$1", "positioning": "p",
        "app_store_rating": 4.0, "app_store_reviews": 10, "shopify_native": True,
        "models_tracked": 4, "changelog": [{"date": "2026-09-13", "note": "Added Grok support"}],
    },
    {
        "name": "QuietOne", "pricing": "$1", "positioning": "p",
        "app_store_rating": None, "app_store_reviews": 0, "shopify_native": False,
        "models_tracked": 2, "changelog": [{"date": "2026-06-01", "note": "Old change"}],
    },
    {
        "name": "NeverChanged", "pricing": "$1", "positioning": "p",
        "app_store_rating": 4.9, "app_store_reviews": 5, "shopify_native": True,
        "models_tracked": 1, "changelog": [],
    },
]


def test_days_since_last_change_computed_against_reference_date():
    report = CompetitiveMonitoringBot(COMPETITORS).scan(reference_date=REFERENCE, alert_window_days=14)
    row = next(r for r in report.rows if r.name == "RecentMover")
    assert row.last_change_days_ago == 3


def test_recent_change_within_window_generates_alert():
    report = CompetitiveMonitoringBot(COMPETITORS).scan(reference_date=REFERENCE, alert_window_days=14)
    assert any("RecentMover" in a for a in report.alerts)


def test_change_outside_window_does_not_alert():
    report = CompetitiveMonitoringBot(COMPETITORS).scan(reference_date=REFERENCE, alert_window_days=14)
    assert not any("QuietOne" in a for a in report.alerts)


def test_no_changelog_means_no_change_and_no_alert():
    report = CompetitiveMonitoringBot(COMPETITORS).scan(reference_date=REFERENCE, alert_window_days=14)
    row = next(r for r in report.rows if r.name == "NeverChanged")
    assert row.last_change_note is None
    assert row.to_dict()["last_change"] == "No change"
    assert not any("NeverChanged" in a for a in report.alerts)


def test_differentiation_note_added_when_close_to_our_model_count():
    report = CompetitiveMonitoringBot(COMPETITORS).scan(reference_date=REFERENCE, alert_window_days=14)
    alert = next(a for a in report.alerts if "RecentMover" in a)
    assert "multi-model breadth" in alert


def test_non_shopify_native_reports_correctly():
    report = CompetitiveMonitoringBot(COMPETITORS).scan(reference_date=REFERENCE)
    row = next(r for r in report.rows if r.name == "QuietOne")
    assert row.to_dict()["app_store"] == "n/a — not Shopify-native"
