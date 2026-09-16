"""A small demo seed list of real, publicly-documented merchants, standing
in until a real candidate source (a purchased StoreLeads/BuiltWith export,
or your own list) is wired in — `discover_from_seed_list` /
`discover_from_seed_list_any_platform` both take any list shaped like this.

Most entries here are Shopify merchants; `hibbett.com` is deliberately
included as a confirmed NON-Shopify example (Hibbett Sports runs Salesforce
Commerce Cloud, per public reporting) so this one list exercises both
paths: the strict `scrape` command correctly skips it with a "not Shopify"
error, and `scrape --any-platform` falls through to it via the schema.org/
Open Graph tier.

Category and competitors here are general public knowledge (well-known
industry competitors), not scraped or fabricated. Revenue and contact
details are NOT included here on purpose — they aren't public/scrapable
facts about these companies, so the scraper functions leave them unset
rather than inventing numbers or names for real businesses.

Verify with `is_shopify()` before relying on this list for anything real:
a merchant can migrate platforms, and this list isn't re-checked here.
"""

SEED_DOMAINS: list[dict] = [
    {
        "domain": "allbirds.com", "category": "Footwear",
        "product_category": "sustainable footwear",
        "competitors": ["Rothy's", "Veja"],
    },
    {
        "domain": "gymshark.com", "category": "Apparel",
        "product_category": "activewear",
        "competitors": ["Alphalete", "Nike Training"],
    },
    {
        "domain": "kyliecosmetics.com", "category": "Beauty",
        "product_category": "cosmetics",
        "competitors": ["Fenty Beauty", "Rare Beauty"],
    },
    {
        "domain": "colourpop.com", "category": "Beauty",
        "product_category": "cosmetics",
        "competitors": ["e.l.f. Cosmetics", "NYX"],
    },
    {
        "domain": "elfcosmetics.com", "brand_name": "e.l.f. Cosmetics", "category": "Beauty",
        "product_category": "cosmetics",
        "competitors": ["ColourPop", "NYX", "Fenty Beauty"],
    },
    {
        "domain": "brooklinen.com", "category": "Home",
        "product_category": "bedding",
        "competitors": ["Parachute", "Boll & Branch"],
    },
    {
        "domain": "chubbiesshorts.com", "category": "Apparel",
        "product_category": "men's shorts",
        "competitors": ["Vuori", "Marine Layer"],
    },
    {
        "domain": "mvmt.com", "category": "Accessories",
        "product_category": "watches",
        "competitors": ["Daniel Wellington", "Nixon"],
    },
    {
        "domain": "deathwishcoffee.com", "category": "Food & Beverage",
        "product_category": "coffee",
        "competitors": ["Black Rifle Coffee", "Koffee Kult"],
    },
    {
        # Confirmed NOT Shopify (Salesforce Commerce Cloud) — see module docstring.
        "domain": "hibbett.com", "brand_name": "Hibbett", "category": "Footwear",
        "product_category": "athletic footwear and apparel",
        "competitors": ["Foot Locker", "Dick's Sporting Goods", "Academy Sports + Outdoors"],
    },
]
