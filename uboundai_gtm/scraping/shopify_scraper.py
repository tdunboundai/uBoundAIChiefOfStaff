"""Direct-scraping enrichment for the Prospecting Bot.

Two things a Shopify store leaks publicly, with no auth and no paid API:

1. A fingerprint that confirms it's actually running Shopify (response
   headers like `X-Shopify-Stage`, or `cdn.shopify.com` / the `Shopify.shop`
   JS global in the homepage HTML).
2. `/products.json` — most stores expose this unauthenticated, returning
   real product titles, prices and stock status. That's exactly what
   `known_facts` (`price_usd`, `discontinued`) needs for the Audit Bot's
   hallucination check.

What this file deliberately does NOT do: estimate revenue, guess
competitors, or invent a contact. None of that is present in what a store
exposes publicly, and it's not this module's job to make it up —
`monthly_revenue_est` comes back `None` and `contact` comes back empty
until a real firmographic/contact-enrichment source is wired in (see
README). Discovering *which* domains to check at all is also out of scope
here; that's `seed_domains.py` (or, in a real deployment, a purchased
Shopify-store list) feeding this module a list of candidates.
"""
from __future__ import annotations

from typing import Callable

import requests

SHOPIFY_HEADER_MARKERS = ("x-shopify-stage", "x-shopid", "x-sorting-hat-shopid")
SHOPIFY_HTML_MARKERS = ("cdn.shopify.com", "Shopify.shop", "shopify-checkout-api-token")

GetFn = Callable[..., requests.Response]


class NotShopifyError(RuntimeError):
    """Raised when a candidate domain doesn't fingerprint as Shopify."""


def is_shopify(domain: str, get_fn: GetFn = requests.get, timeout: float = 10.0) -> bool:
    resp = get_fn(f"https://{domain}/", timeout=timeout)
    resp.raise_for_status()
    header_keys = {k.lower() for k in resp.headers}
    if any(marker in header_keys for marker in SHOPIFY_HEADER_MARKERS):
        return True
    return any(marker in resp.text for marker in SHOPIFY_HTML_MARKERS)


def fetch_products(domain: str, get_fn: GetFn = requests.get, limit: int = 5, timeout: float = 10.0) -> list[dict]:
    resp = get_fn(f"https://{domain}/products.json", params={"limit": limit}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    products = []
    for p in data.get("products", []):
        variants = p.get("variants", [])
        price = float(variants[0]["price"]) if variants and variants[0].get("price") is not None else None
        available = any(v.get("available") for v in variants) if variants else None
        products.append({"title": p.get("title", ""), "price_usd": price, "available": available})
    return products


def pick_flagship(products: list[dict]) -> dict | None:
    """Picks the product to anchor `known_facts` on. v1: first product with
    a known price. A real deployment might prefer a best-seller signal,
    which needs a different endpoint (order data isn't public)."""
    for p in products:
        if p.get("price_usd") is not None:
            return p
    return products[0] if products else None


def build_prospect(seed: dict, get_fn: GetFn = requests.get) -> dict:
    """Turns one seed entry (`{"domain", "category", ...}`) into a prospect
    dict shaped exactly like `data/prospects_mock.json`, so it drops straight
    into `ProspectingBot(prospects=...)` with no other code changes."""
    domain = seed["domain"]
    if not is_shopify(domain, get_fn=get_fn):
        raise NotShopifyError(f"{domain} does not fingerprint as a Shopify store")

    flagship = pick_flagship(fetch_products(domain, get_fn=get_fn))
    known_facts: dict = {}
    if flagship:
        known_facts["flagship_product"] = flagship["title"]
        if flagship.get("price_usd") is not None:
            known_facts["price_usd"] = flagship["price_usd"]
        if flagship.get("available") is not None:
            known_facts["discontinued"] = not flagship["available"]

    brand_name = seed.get("brand_name") or _guess_brand_name(domain)
    return {
        "id": domain.replace(".", "-"),
        "store": brand_name,
        "domain": domain,
        "brand_name": brand_name,
        "category": seed["category"],
        "monthly_revenue_est": None,  # not scrapable; needs a firmographic source (see README)
        "competitors": list(seed.get("competitors", [])),
        "product_category": seed.get("product_category", seed["category"]),
        "known_facts": known_facts,
        "contact": seed.get("contact") or {"name": None, "email": None},
    }


def discover_from_seed_list(seeds: list[dict], get_fn: GetFn = requests.get) -> tuple[list[dict], list[str]]:
    """Builds a prospect for every seed it can reach and confirm as Shopify;
    anything that fails (network error, not actually Shopify, bad response
    shape) is skipped and reported in `errors` instead of aborting the batch."""
    prospects: list[dict] = []
    errors: list[str] = []
    for seed in seeds:
        try:
            prospects.append(build_prospect(seed, get_fn=get_fn))
        except (NotShopifyError, requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"{seed.get('domain', '?')}: {exc}")
    return prospects, errors


def _guess_brand_name(domain: str) -> str:
    label = domain.split(".")[0]
    return label.replace("-", " ").replace("_", " ").title()
