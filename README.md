# UnboundAI GTM Bots

Five bots for UnboundAI's go-to-market motion: sell an AI-visibility-across-LLMs
product to Shopify retailers by using the product itself as the lead magnet.

Concept mockup (pipeline diagram + wireframe screens) reviewed before this
build: see the shared design canvas from the GTM concept review.

## The five bots

| # | Bot | Module | What it does |
|---|-----|--------|---------------|
| 1 | **Audit-Generation** | `uboundai_gtm/bots/audit_bot.py` | Queries Gemini, ChatGPT, Perplexity, Grok and Claude like a shopper would, and scores what each says: mentioned?, sentiment, share of voice vs. named competitors, and hallucination flags (wrong price, falsely-claimed discontinued). Core product **and** the free lead-magnet report. |
| 2 | **Prospecting** | `uboundai_gtm/bots/prospecting_bot.py` | Scores Shopify stores against an ICP filter and auto-runs the Audit Bot on the top N, so the "visibility gap" on the lead list is real, not guessed. |
| 3 | **Outreach & Content-Personalization** | `uboundai_gtm/bots/outreach_bot.py` | Turns an audit's real finding into a personalized email, LinkedIn DM, ad copy and landing headline. Generates content only — no send integration. |
| 4 | **Competitive & Category-Monitoring** | `uboundai_gtm/bots/competitive_bot.py` | Tracks named competitors (LLMrefs, Shop Mentions, FSEO, Semrush's LLM add-on, Lexsis) and surfaces recent pricing/positioning/changelog moves as alerts. |
| 5 | **GEO Content** | `uboundai_gtm/bots/geo_content_bot.py` | A content board (Draft/Scheduled/Published/Cited) plus a citation check that dogfoods the Audit Bot's own capability on UnboundAI itself. X/Grok-tagged content is a distinct channel, since Grok grounds answers in live X activity. |

`uboundai_gtm/pipeline.py` wires **Prospecting → Audit → Outreach** into one
call. Competitive Monitoring and GEO Content are deliberately independent,
parallel tracks — they don't feed the main pipeline, matching the reviewed
concept diagram.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in whichever provider keys you have
```

No key is required to run anything: every bot degrades gracefully when a
provider key is missing (the Audit Bot marks that model "no API key
configured — skipped" instead of failing), so the whole pipeline is runnable
today against the mock prospect/competitor data with zero keys.

## Run it

```bash
# Bot 2 — score prospects, optionally auto-audit the top N
python -m uboundai_gtm.cli prospect --audit-top 2

# Bot 1 — audit one of the mock prospects, or a domain you name yourself
python -m uboundai_gtm.cli audit --prospect acme-outdoor
python -m uboundai_gtm.cli audit --domain mystore.com --brand "My Store" --category "hiking boots" --competitor Rival --price 89

# Bot 3 — generate a personalized pitch for one prospect (--llm-copy uses Claude for the email body)
python -m uboundai_gtm.cli outreach --prospect acme-outdoor --llm-copy

# Bot 4 — scan tracked competitors for recent moves
python -m uboundai_gtm.cli competitive

# Bot 2 (live) — discover real Shopify stores via direct scraping (fingerprint + /products.json),
# from the built-in demo seed list; unreachable/non-Shopify domains are skipped, not fatal
python -m uboundai_gtm.cli scrape --score

# Bot 2 (live, any platform) — same, but accepts non-Shopify domains too via a schema.org
# JSON-LD / Open Graph fallback (lower confidence; check the "platform" field on each result)
python -m uboundai_gtm.cli scrape --any-platform --score

# Bot 5 — demo content board, optionally checking real citations
python -m uboundai_gtm.cli geo --check-citations

# Full pipeline: Prospecting -> Audit -> Outreach
python -m uboundai_gtm.cli pipeline --top-n 3
```

Every command prints JSON to stdout.

## Tests

```bash
pytest
```

All 5 bots and the pipeline are tested against a `FakeLLMClient`
(`tests/conftest.py`) — no network calls, no API keys needed.

## Architecture notes / known limitations

- **LLM clients** (`uboundai_gtm/llm/`) call each provider's REST API
  directly via `requests`, one thin client per provider sharing a common
  `LLMClient` interface. Add a provider by subclassing `LLMClient` (or
  `_openai_compatible.OpenAICompatibleClient` for OpenAI-shaped APIs) and
  registering it in `llm/registry.py`.
- **Prospecting and competitor data are mocked by default**
  (`uboundai_gtm/data/*.json`), read through `uboundai_gtm.data.load_prospects()`
  / `load_competitors()`. **`uboundai_gtm/scraping/`** is a real, working
  alternative source for prospects: `shopify_scraper.py` confirms a domain
  is actually Shopify (response-header/HTML fingerprint) and pulls real
  product names/prices/stock from the unauthenticated `/products.json`
  endpoint most stores expose, which populates `known_facts` for the Audit
  Bot's hallucination check. It does **not** invent revenue, competitors,
  or contact info for scraped stores — those aren't public/scrapable facts,
  so they come back `None`/empty until a real firmographic or contact-
  enrichment source (BuiltWith, SimilarWeb, StoreLeads, Apollo/Clearbit) is
  wired in. `seed_domains.py` ships a small demo list of real, well-known
  Shopify merchants standing in for a purchased store list; swap it for
  your own once you have one — same dict shape, no code changes needed.
  Sourcing *candidate* domains at scale (vs. enriching known ones) is a
  discovery problem better solved by a store-list provider than a crawler;
  see the `scrape` CLI command above.
- **Non-Shopify domains** are supported via `uboundai_gtm/scraping/generic_scraper.py`
  (`scrape --any-platform`), which is a deliberately separate, lower-confidence
  path: it tries the Shopify fast path first, then falls back to schema.org
  Product JSON-LD, then Open Graph product tags. There's no universal
  `/products.json` equivalent across platforms, so coverage is inconsistent
  by nature — every result carries a `platform` field (`"shopify"` |
  `"generic"` | `"unknown"`) so low-confidence leads can be told apart from
  the reliable Shopify ones. This exists as a secondary net, not a pivot:
  the core pitch and ICP stay Shopify-specific.
- **Sentiment and hallucination detection are heuristic v1** (keyword
  counting, regex price/discontinued matching in `audit_bot.py`). Good
  enough to catch obvious cases; an LLM-as-judge pass is the natural
  upgrade once this is validated against real audits.
- **ICP scoring is a placeholder** (`prospecting_bot._score`): a log-scale
  fit around a revenue sweet spot. Replace with real firmographic/ad-spend/
  tech-stack signals once a live data source exists.
- **GEO Content Bot has no persistence** — `cli.py geo` seeds a fresh demo
  board on every run. A real deployment backs `ContentCard`s with a DB/CMS.
- **Outreach never sends anything.** It returns an `OutreachPackage`
  (email/DM/ad copy/headline as data); wiring a send integration (SMTP,
  SendGrid, LinkedIn API) is an explicit, separate decision.
