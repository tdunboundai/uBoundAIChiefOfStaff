from __future__ import annotations

from uboundai_gtm.bots.geo_content_bot import ContentChannel, ContentStatus, GEOContentBot


def test_add_card_and_board_grouping():
    bot = GEOContentBot()
    bot.add_card("Draft post", ContentChannel.STANDARD, ContentStatus.DRAFT)
    bot.add_card("Scheduled post", ContentChannel.X_GROK, ContentStatus.SCHEDULED)
    board = bot.board()
    assert len(board["Draft"]) == 1
    assert len(board["Scheduled"]) == 1
    assert board["Scheduled"][0]["channel"] == "X · Grok-priority"


def test_move_changes_column():
    bot = GEOContentBot()
    card = bot.add_card("Post", ContentChannel.STANDARD, ContentStatus.DRAFT)
    bot.move(card.id, ContentStatus.PUBLISHED)
    board = bot.board()
    assert board["Draft"] == []
    assert len(board["Published"]) == 1


def test_check_citation_moves_card_to_cited_column(fake_client):
    bot = GEOContentBot({"claude": fake_client("claude", "UnboundAI has great coverage of this topic.")})
    card = bot.add_card("Flagship post", ContentChannel.STANDARD, ContentStatus.PUBLISHED)

    cited_by = bot.check_citation(card.id, "what's a good resource?", "UnboundAI")

    assert cited_by == ["claude"]
    board = bot.board()
    assert board["Published"] == []
    assert len(board["Cited"]) == 1
    assert board["Cited"][0]["cited_by"] == ["claude"]


def test_check_citation_no_match_leaves_card_in_published(fake_client):
    bot = GEOContentBot({"gemini": fake_client("gemini", "Try a competitor's guide instead.")})
    card = bot.add_card("Flagship post", ContentChannel.STANDARD, ContentStatus.PUBLISHED)

    cited_by = bot.check_citation(card.id, "what's a good resource?", "UnboundAI")

    assert cited_by == []
    board = bot.board()
    assert len(board["Published"]) == 1
    assert board["Cited"] == []
