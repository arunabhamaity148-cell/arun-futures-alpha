"""Tests for NewsGuard engine."""
import time

import pytest

from trader_arun.core.types import NewsAction, NewsItem
from trader_arun.newsguard.engine import NewsGuard


def _item(headline, source="test", severity="MEDIUM", tags=None):
    return NewsItem(
        source=source, headline=headline, severity=severity,
        pair_tags=tags or ["*"], url="",
        published_at=time.time(), received_at=time.time(),
    )


def test_allow_when_no_news():
    ng = NewsGuard()
    state = ng.state("BTC")
    assert state.action == NewsAction.ALLOW


def test_block_on_critical_news():
    ng = NewsGuard()
    ng.ingest([_item("FOMC rate decision announced", severity="MEDIUM")])
    state = ng.state("BTC")
    assert state.action == NewsAction.BLOCK
    assert len(state.blocking_items) >= 1


def test_reduce_on_high_news():
    ng = NewsGuard()
    ng.ingest([_item("PCE inflation data release", severity="MEDIUM")])
    state = ng.state("BTC")
    assert state.action == NewsAction.REDUCE


def test_dedup_same_headline():
    ng = NewsGuard()
    ng.ingest([_item("FOMC rate decision")])
    ng.ingest([_item("FOMC rate decision")])  # duplicate
    state = ng.state("BTC")
    # Should only count once.
    assert len(state.blocking_items) == 1


def test_provider_unavailable_blocks():
    ng = NewsGuard()
    ng.mark_provider_unavailable()
    state = ng.state("BTC")
    assert state.action == NewsAction.BLOCK


def test_low_severity_not_tracked():
    ng = NewsGuard()
    ng.ingest([_item("random partnership announcement", severity="LOW")])
    state = ng.state("BTC")
    assert state.action == NewsAction.ALLOW


def test_pair_specific_filtering():
    ng = NewsGuard()
    # News tagged only for ETH, no rule with explicit pair_tags matches.
    # "lawsuit" rule has empty pair_tags, so item's tags are preserved.
    ng.ingest([_item("ETH lawsuit filed", severity="MEDIUM", tags=["ETH"])])
    btc_state = ng.state("BTC")
    eth_state = ng.state("ETH")
    assert btc_state.action == NewsAction.ALLOW  # BTC not tagged
    assert eth_state.action == NewsAction.ALLOW  # MEDIUM severity → ALLOW
