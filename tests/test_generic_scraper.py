from __future__ import annotations

import requests

from uboundai_gtm.scraping.generic_scraper import (
    build_prospect_generic,
    discover_from_seed_list_any_platform,
    extract_jsonld_product,
    extract_opengraph_product,
    fetch_generic_product_signal,
)

JSONLD_FLAT = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Product", "name": "Storm Shell Jacket",
 "offers": {"@type": "Offer", "price": "150.00", "availability": "https://schema.org/InStock"}}
</script>
</head></html>
"""

JSONLD_GRAPH = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "WebPage", "name": "Home"},
  {"@type": "Product", "name": "Trail Runner", "offers": [{"price": "89.99", "availability": "http://schema.org/OutOfStock"}]}
]}
</script>
</head></html>
"""

JSONLD_MALFORMED = """
<html><head><script type="application/ld+json">{not valid json</script></head></html>
"""

OG_HTML = """
<html><head>
<meta property="og:title" content="Camp Cooler 45QT" />
<meta property="product:price:amount" content="249.00">
<meta property="product:availability" content="in stock">
</head></html>
"""

NO_SIGNAL_HTML = "<html><head><title>Just a regular page</title></head></html>"


class FakeResponse:
    def __init__(self, *, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_extract_jsonld_flat_product():
    product = extract_jsonld_product(JSONLD_FLAT)
    assert product == {"title": "Storm Shell Jacket", "price_usd": 150.0, "available": True}


def test_extract_jsonld_product_inside_graph():
    product = extract_jsonld_product(JSONLD_GRAPH)
    assert product["title"] == "Trail Runner"
    assert product["price_usd"] == 89.99
    assert product["available"] is False


def test_extract_jsonld_returns_none_on_malformed_json():
    assert extract_jsonld_product(JSONLD_MALFORMED) is None


def test_extract_jsonld_returns_none_when_no_ld_json_present():
    assert extract_jsonld_product(NO_SIGNAL_HTML) is None


def test_extract_opengraph_product():
    product = extract_opengraph_product(OG_HTML)
    assert product == {"title": "Camp Cooler 45QT", "price_usd": 249.0, "available": True}


def test_extract_opengraph_returns_none_when_absent():
    assert extract_opengraph_product(NO_SIGNAL_HTML) is None


def test_fetch_generic_product_signal_prefers_jsonld_over_og():
    combined_html = JSONLD_FLAT + OG_HTML

    def get_fn(url, timeout=None):
        return FakeResponse(text=combined_html)

    signal = fetch_generic_product_signal("store.com", get_fn=get_fn)
    assert signal["title"] == "Storm Shell Jacket"


def test_fetch_generic_product_signal_falls_back_to_og():
    def get_fn(url, timeout=None):
        return FakeResponse(text=OG_HTML)

    signal = fetch_generic_product_signal("store.com", get_fn=get_fn)
    assert signal["title"] == "Camp Cooler 45QT"


def test_build_prospect_generic_uses_shopify_tier_when_available():
    prospect = build_prospect_generic({"domain": "shop.com", "category": "Outdoor"}, get_fn=_shopify_get_fn())
    assert prospect["platform"] == "shopify"
    assert prospect["known_facts"]["flagship_product"] == "Duffel"


def _shopify_get_fn():
    class Resp(FakeResponse):
        def json(self):
            return {"products": [{"title": "Duffel", "variants": [{"price": "39.00", "available": True}]}]}

    def get_fn(url, timeout=None, params=None):
        if url.endswith("/"):
            return FakeResponse(text="<script src='https://cdn.shopify.com/x.js'></script>")
        return Resp(text="")
    return get_fn


def test_build_prospect_generic_falls_back_to_jsonld_when_not_shopify():
    def get_fn(url, timeout=None, params=None):
        return FakeResponse(text=JSONLD_FLAT)

    prospect = build_prospect_generic({"domain": "woo-store.com", "category": "Apparel"}, get_fn=get_fn)
    assert prospect["platform"] == "generic"
    assert prospect["known_facts"]["flagship_product"] == "Storm Shell Jacket"
    assert prospect["monthly_revenue_est"] is None
    assert prospect["contact"] == {"name": None, "email": None}


def test_build_prospect_generic_no_signal_still_returns_a_lead():
    def get_fn(url, timeout=None, params=None):
        return FakeResponse(text=NO_SIGNAL_HTML)

    prospect = build_prospect_generic({"domain": "mystery-store.com", "category": "Apparel"}, get_fn=get_fn)
    assert prospect["platform"] == "unknown"
    assert prospect["known_facts"] == {}


def test_discover_from_seed_list_any_platform_skips_network_failures():
    def get_fn(url, timeout=None, params=None):
        raise requests.ConnectionError("unreachable")

    prospects, errors = discover_from_seed_list_any_platform(
        [{"domain": "bad.com", "category": "Apparel"}], get_fn=get_fn
    )
    assert prospects == []
    assert "bad.com" in errors[0]
