"""Mock datasets standing in for real Shopify/competitor data sources.

Swap `load_prospects` / `load_competitors` for real API-backed loaders
(BuiltWith, SimilarWeb, Shopify App Store, etc.) once those integrations exist;
every bot consumes these through the loader functions below, not the JSON
files directly, so the swap is contained here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent


def load_prospects() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "prospects_mock.json").read_text())


def load_competitors() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "competitors_mock.json").read_text())


__all__ = ["load_prospects", "load_competitors", "DATA_DIR"]
