"""Bot 5 — GEO Content Bot.

Manages a lightweight content board (Draft / Scheduled / Published / Cited)
and checks whether UnboundAI's own content is getting cited by the LLMs it
tracks — dogfooding the product's own core capability on itself.

X/Grok-tagged content is a distinct channel: Grok grounds its answers in
live X activity in a way the other four models don't, so content aimed at
Grok citations is written and timed differently (a live X post, not a blog).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..llm.base import LLMClient, LLMRequestError, MissingAPIKeyError


class ContentChannel(str, Enum):
    STANDARD = "Standard"
    X_GROK = "X · Grok-priority"


class ContentStatus(str, Enum):
    DRAFT = "Draft"
    SCHEDULED = "Scheduled"
    PUBLISHED = "Published"


@dataclass
class ContentCard:
    id: str
    title: str
    channel: ContentChannel
    status: ContentStatus = ContentStatus.DRAFT
    cited_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = {"id": self.id, "title": self.title, "channel": self.channel.value, "status": self.status.value}
        if self.cited_by:
            data["cited_by"] = list(self.cited_by)
        return data


class GEOContentBot:
    def __init__(self, clients: dict[str, LLMClient] | None = None):
        self.clients = clients or {}
        self._cards: dict[str, ContentCard] = {}
        self._next_id = 1

    def add_card(
        self, title: str, channel: ContentChannel, status: ContentStatus = ContentStatus.DRAFT
    ) -> ContentCard:
        card = ContentCard(id=f"card-{self._next_id}", title=title, channel=channel, status=status)
        self._cards[card.id] = card
        self._next_id += 1
        return card

    def move(self, card_id: str, status: ContentStatus) -> ContentCard:
        card = self._cards[card_id]
        card.status = status
        return card

    def check_citation(self, card_id: str, query: str, brand_name: str) -> list[str]:
        """Asks every configured LLM `query` and records which ones mention
        `brand_name` in the answer, treating that as a citation. Meaningful
        only once the card is PUBLISHED."""
        card = self._cards[card_id]
        cited_by: list[str] = []
        for provider, client in self.clients.items():
            try:
                answer = client.ask(query)
            except (MissingAPIKeyError, LLMRequestError):
                continue
            if brand_name.lower() in answer.text.lower():
                cited_by.append(provider)
        card.cited_by = sorted(set(card.cited_by) | set(cited_by))
        return cited_by

    def board(self) -> dict[str, list[dict]]:
        columns: dict[str, list[dict]] = {"Draft": [], "Scheduled": [], "Published": [], "Cited": []}
        for card in self._cards.values():
            if card.cited_by:
                columns["Cited"].append(card.to_dict())
            else:
                columns[card.status.value].append(card.to_dict())
        return columns
