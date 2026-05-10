"""Tests for monitor.py signal filtering logic."""
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

import common
from monitor import _is_tradeable, _poll_whale


class TestPollWhale:
    def test_filters_known_ids(self):
        client = MagicMock()
        client.get_trades.return_value = [
            {"id": "trade1", "side": "BUY"},
            {"id": "trade2", "side": "BUY"},
            {"id": "trade3", "side": "BUY"},
        ]
        known = {"trade1", "trade2"}
        result = _poll_whale(client, "0xaddr", known)
        assert len(result) == 1
        assert result[0]["id"] == "trade3"

    def test_all_known_returns_empty(self):
        client = MagicMock()
        client.get_trades.return_value = [{"id": "t1"}, {"id": "t2"}]
        result = _poll_whale(client, "0xaddr", {"t1", "t2"})
        assert result == []

    def test_empty_response(self):
        client = MagicMock()
        client.get_trades.return_value = []
        result = _poll_whale(client, "0xaddr", set())
        assert result == []


class TestIsTradeable:
    def _make_client(self, liquidity=50_000, hours_left=200):
        client = MagicMock()
        end_dt = (datetime.now(timezone.utc) + timedelta(hours=hours_left)).isoformat()
        client.get_market.return_value = {
            "liquidity": liquidity,
            "end_date_iso": end_dt,
            "question": "Will X happen?",
        }
        return client

    def _make_trade(self, side="BUY", token_id="tok1", condition_id="cond1"):
        return {
            "id": "trade123",
            "side": side,
            "asset_id": token_id,
            "market": condition_id,
            "price": "0.55",
            "size": "1000",
        }

    def _make_state(self, active_positions=None, daily_log=None):
        return {
            "active_positions": active_positions or {},
            "daily_trade_log": daily_log or [],
        }

    def test_valid_trade_approved(self):
        client = self._make_client(liquidity=50_000, hours_left=200)
        trade = self._make_trade(side="BUY")
        state = self._make_state()
        result = _is_tradeable(trade, client, state)
        assert result is not None
        assert result["token_id"] == "tok1"

    def test_sell_side_rejected(self):
        client = self._make_client()
        trade = self._make_trade(side="SELL")
        result = _is_tradeable(trade, client, self._make_state())
        assert result is None

    def test_already_holding_rejected(self):
        client = self._make_client()
        trade = self._make_trade(token_id="tok1")
        state = self._make_state(active_positions={"pos1": {"token_id": "tok1", "status": "open"}})
        result = _is_tradeable(trade, client, state)
        assert result is None

    def test_low_liquidity_rejected(self):
        client = self._make_client(liquidity=5_000)
        result = _is_tradeable(self._make_trade(), client, self._make_state())
        assert result is None

    def test_market_closing_soon_rejected(self):
        client = self._make_client(hours_left=10)
        result = _is_tradeable(self._make_trade(), client, self._make_state())
        assert result is None

    def test_daily_limit_rejected(self):
        client = self._make_client()
        today = datetime.now(timezone.utc).date().isoformat()
        log = [f"{today}T{h:02d}:00:00+00:00" for h in range(10)]
        state = self._make_state(daily_log=log)
        result = _is_tradeable(self._make_trade(), client, state)
        assert result is None

    def test_enriched_signal_has_market_info(self):
        client = self._make_client(liquidity=80_000)
        result = _is_tradeable(self._make_trade(), client, self._make_state())
        assert result is not None
        assert result["market_liquidity"] == 80_000
        assert "end_date_iso" in result
        assert result["market_question"] == "Will X happen?"
