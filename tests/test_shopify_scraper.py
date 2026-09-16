from __future__ import annotations

import requests

from uboundai_gtm.scraping.shopify_scraper import (
    NotShopifyError,
    build_prospect,
    discover_from_seed_list,
    fetch_products,
    is_shopify,
    pick_flagship,
)


class FakeResponse:
    def __init__(self, *, status_code=200, headers=None, text="", json_data=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self._json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


def fake_get_factory(homepage: FakeResponse, products: FakeResponse | None = None):
    def _get(url, timeout=None, params=None):
        if url.endswith("/"):
            return homepage
        return products
    return _get


def test_is_shopify_detects_header_marker():
    get_fn = fake_get_factory(FakeResponse(headers={"X-ShopId": "123"}, text="plain html"))
    assert is_shopify("store.com", get_fn=get_fn) is True


def test_is_shopify_detects_html_marker():
    get_fn = fake_get_factory(FakeResponse(text="<script src='https://cdn.shopify.com/foo.js'></script>"))
    assert is_shopify("store.com", get_fn=get_fn) is True


def test_is_shopify_false_when_no_markers_present():
    get_fn = fake_get_factory(FakeResponse(text="<html>just a regular site</html>"))
    assert is_shopify("store.com", get_fn=get_fn) is False


def test_fetch_products_parses_title_price_and_availability():
    products_json = {
        "products": [
            {"title": "Trail Shoe", "variants": [{"price": "89.00", "available": True}]},
            {"title": "Sold Out Jacket", "variants": [{"price": "150.00", "available": False}]},
        ]
    }
    get_fn = fake_get_factory(FakeResponse(), FakeResponse(json_data=products_json))
    products = fetch_products("store.com", get_fn=get_fn)

    assert products[0] == {"title": "Trail Shoe", "price_usd": 89.0, "available": True}
    assert products[1]["available"] is False


def test_pick_flagship_prefers_product_with_known_price():
    products = [{"title": "No price", "price_usd": None, "available": None}, {"title": "Priced", "price_usd": 42.0, "available": True}]
    assert pick_flagship(products)["title"] == "Priced"


def test_pick_flagship_returns_none_for_empty_list():
    assert pick_flagship([]) is None


def test_build_prospect_shapes_data_like_mock_dataset():
    seed = {"domain": "trailco.com", "category": "Outdoor", "competitors": ["Rival"]}
    homepage = FakeResponse(headers={"X-Shopify-Stage": "production"})
    products = FakeResponse(json_data={"products": [{"title": "Duffel", "variants": [{"price": "39.00", "available": True}]}]})
    get_fn = fake_get_factory(homepage, products)

    prospect = build_prospect(seed, get_fn=get_fn)

    assert prospect["domain"] == "trailco.com"
    assert prospect["brand_name"] == "Trailco"
    assert prospect["monthly_revenue_est"] is None
    assert prospect["known_facts"] == {"flagship_product": "Duffel", "price_usd": 39.0, "discontinued": False}
    assert prospect["contact"] == {"name": None, "email": None}


def test_build_prospect_raises_when_not_shopify():
    seed = {"domain": "notshopify.com", "category": "Outdoor"}
    get_fn = fake_get_factory(FakeResponse(text="nothing here"))
    try:
        build_prospect(seed, get_fn=get_fn)
        assert False, "expected NotShopifyError"
    except NotShopifyError:
        pass


def test_discover_from_seed_list_skips_failures_without_raising():
    good_seed = {"domain": "good.com", "category": "Outdoor"}
    bad_seed = {"domain": "bad.com", "category": "Outdoor"}

    def get_fn(url, timeout=None, params=None):
        if "good.com" in url:
            if url.endswith("/"):
                return FakeResponse(headers={"X-ShopId": "1"})
            return FakeResponse(json_data={"products": []})
        raise requests.ConnectionError("unreachable")

    prospects, errors = discover_from_seed_list([good_seed, bad_seed], get_fn=get_fn)

    assert len(prospects) == 1
    assert prospects[0]["domain"] == "good.com"
    assert len(errors) == 1
    assert "bad.com" in errors[0]
