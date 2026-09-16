from .generic_scraper import (
    build_prospect_generic,
    discover_from_seed_list_any_platform,
    extract_jsonld_product,
    extract_opengraph_product,
    fetch_generic_product_signal,
)
from .seed_domains import SEED_DOMAINS
from .shopify_scraper import (
    NotShopifyError,
    build_prospect,
    discover_from_seed_list,
    fetch_products,
    is_shopify,
    pick_flagship,
)

__all__ = [
    "SEED_DOMAINS",
    "NotShopifyError",
    "build_prospect",
    "discover_from_seed_list",
    "fetch_products",
    "is_shopify",
    "pick_flagship",
    "build_prospect_generic",
    "discover_from_seed_list_any_platform",
    "extract_jsonld_product",
    "extract_opengraph_product",
    "fetch_generic_product_signal",
]
