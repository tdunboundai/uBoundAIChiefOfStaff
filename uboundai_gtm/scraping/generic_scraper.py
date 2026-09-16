"""Platform-agnostic product-signal extraction — the fallback tier for
domains that aren't Shopify (or where that hasn't been confirmed).

There's no universal `/products.json` equivalent across platforms, but most
e-commerce sites (WooCommerce, Magento, BigCommerce, custom builds) embed
schema.org Product markup as JSON-LD so they get rich results in Google
Search. That's the best cross-platform signal available without a headless
browser or a per-page LLM call, so it's tier 1 here; Open Graph product tags
are a thinner but still common tier 2.

This is deliberately lower-confidence than `shopify_scraper.py`'s
`/products.json` path: JSON-LD/OG coverage is inconsistent across the web,
so `known_facts` coming out of here should be treated as "best effort," not
verified fact the way a Shopify store's own product feed is.
"""
from __future__ import annotations

import json
import re

import requests

from .shopify_scraper import GetFn, _guess_brand_name, fetch_products, is_shopify

_JSONLD_BLOCK_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_META_TAG_RE = re.compile(r"<meta\s+([^>]+?)/?>", re.IGNORECASE)
_META_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"|([\w:-]+)\s*=\s*\'([^\']*)\'')


def _availability_to_bool(value: str | None) -> bool | None:
    if not value:
        return None
    if "InStock" in value or "LimitedAvailability" in value or "PreOrder" in value:
        return True
    if "OutOfStock" in value or "Discontinued" in value or "SoldOut" in value:
        return False
    return None


def _first_product_node(nodes: list) -> dict | None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "Product" in types:
            return node
    return None


def extract_jsonld_product(html: str) -> dict | None:
    """Parses every `<script type="application/ld+json">` block looking for
    a schema.org Product node (flat, in a list, or nested under `@graph`)."""
    for raw in _JSONLD_BLOCK_RE.findall(html):
        try:
            parsed = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue

        if isinstance(parsed, dict) and "@graph" in parsed:
            nodes = parsed["@graph"]
        elif isinstance(parsed, list):
            nodes = parsed
        else:
            nodes = [parsed]

        product = _first_product_node(nodes)
        if product is None:
            continue

        offers = product.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        offers = offers or {}

        price = offers.get("price")
        try:
            price_usd = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_usd = None

        return {
            "title": product.get("name", ""),
            "price_usd": price_usd,
            "available": _availability_to_bool(offers.get("availability")),
        }
    return None


def _parse_meta_tags(html: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for tag_body in _META_TAG_RE.findall(html):
        attrs: dict[str, str] = {}
        for m in _META_ATTR_RE.finditer(tag_body):
            key = m.group(1) or m.group(3)
            val = m.group(2) if m.group(2) is not None else m.group(4)
            attrs[key.lower()] = val
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            tags[key] = attrs["content"]
    return tags


def extract_opengraph_product(html: str) -> dict | None:
    """Falls back to Open Graph product tags when no JSON-LD Product exists."""
    tags = _parse_meta_tags(html)
    title = tags.get("og:title")
    price = tags.get("product:price:amount")
    availability = tags.get("product:availability")

    if not title and price is None:
        return None

    try:
        price_usd = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_usd = None

    available = None
    if availability:
        available = availability.strip().lower() == "in stock"

    return {"title": title or "", "price_usd": price_usd, "available": available}


def fetch_generic_product_signal(domain: str, get_fn: GetFn = requests.get, timeout: float = 10.0) -> dict | None:
    """Tries JSON-LD first, then Open Graph, on the domain's homepage HTML."""
    resp = get_fn(f"https://{domain}/", timeout=timeout)
    resp.raise_for_status()
    return extract_jsonld_product(resp.text) or extract_opengraph_product(resp.text)


def build_prospect_generic(seed: dict, get_fn: GetFn = requests.get) -> dict:
    """Like `shopify_scraper.build_prospect`, but works on any platform:
    tries the Shopify `/products.json` fast path first (richest data when it
    applies), then falls back to the generic JSON-LD/OG signal. Never raises
    for "not Shopify" — only for a real network/response failure, which the
    caller (`discover_from_seed_list`) already catches."""
    domain = seed["domain"]
    flagship = None
    platform = "unknown"

    if is_shopify(domain, get_fn=get_fn):
        products = fetch_products(domain, get_fn=get_fn)
        flagship = products[0] if products else None
        platform = "shopify"
    else:
        signal = fetch_generic_product_signal(domain, get_fn=get_fn)
        if signal:
            flagship = signal
            platform = "generic"

    known_facts: dict = {}
    if flagship and flagship.get("title"):
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
        "monthly_revenue_est": None,
        "competitors": list(seed.get("competitors", [])),
        "product_category": seed.get("product_category", seed["category"]),
        "known_facts": known_facts,
        "contact": seed.get("contact") or {"name": None, "email": None},
        "platform": platform,  # "shopify" | "generic" | "unknown" — confidence signal, not used by ProspectingBot
    }


def discover_from_seed_list_any_platform(seeds: list[dict], get_fn: GetFn = requests.get) -> tuple[list[dict], list[str]]:
    prospects: list[dict] = []
    errors: list[str] = []
    for seed in seeds:
        try:
            prospects.append(build_prospect_generic(seed, get_fn=get_fn))
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append(f"{seed.get('domain', '?')}: {exc}")
    return prospects, errors
