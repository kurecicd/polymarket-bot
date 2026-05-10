"""Tests for position_manager.py exit condition logic."""
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from position_manager import _check_exit_reason


def _make_client(current_price=0.5):
    client = MagicMock()
    client.get_last_trade_price.return_value = current_price
    client.get_trades.return_value = []
    client.get_book.return_value = {"bids": [{"price": "0.49"}]}
    return client


def _make_position(
    entry_price=0.5,
    profit_target_price=None,
    whale_entry_size_shares=1000.0,
    hours_until_end=200,
    opened_at_ts=None,
):
    if profit_target_price is None:
        profit_target_price = round(entry_price * 1.25, 4)
    end_dt = (datetime.now(timezone.utc) + timedelta(hours=hours_until_end)).isoformat()
    return {
        "token_id": "tok1",
        "condition_id": "cond1",
        "market_question": "Test market",
        "whale_address": "0xwhale",
        "entry_price": entry_price,
        "profit_target_price": profit_target_price,
        "size_shares": 500.0,
        "size_usdc": 250.0,
        "whale_entry_size_shares": whale_entry_size_shares,
        "opened_at_ts": opened_at_ts or int(time.time()) - 3600,
        "end_date_iso": end_dt,
        "status": "open",
    }


class TestCheckExitReason:

    def test_profit_target_triggers(self):
        pos = _make_position(entry_price=0.5, profit_target_price=0.625)
        client = _make_client(current_price=0.63)  # above target
        reason = _check_exit_reason(client, pos)
        assert reason == "profit_target"

    def test_profit_target_not_triggered_below(self):
        pos = _make_position(entry_price=0.5, profit_target_price=0.625)
        client = _make_client(current_price=0.60)  # below target
        client.get_trades.return_value = []
        reason = _check_exit_reason(client, pos)
        assert reason is None

    def test_market_closing_soon_triggers(self):
        pos = _make_position(entry_price=0.5, hours_until_end=10)
        client = _make_client(current_price=0.50)
        reason = _check_exit_reason(client, pos)
        assert reason == "market_closing_soon"

    def test_whale_exiting_triggers(self):
        pos = _make_position(entry_price=0.5, whale_entry_size_shares=1000.0)
        client = _make_client(current_price=0.50)
        # Whale sold 400 shares (40% of 1000) → exceeds 30% threshold
        client.get_trades.return_value = [
            {"asset_id": "tok1", "side": "SELL", "size": "400",
             "token_id": "tok1", "timestamp": str(int(time.time()))},
        ]
        reason = _check_exit_reason(client, pos)
        assert reason == "whale_exiting"

    def test_whale_small_sell_does_not_trigger(self):
        pos = _make_position(entry_price=0.5, whale_entry_size_shares=1000.0)
        client = _make_client(current_price=0.50)
        # Whale sold only 10 shares (1%) — not enough to trigger
        client.get_trades.return_value = [
            {"asset_id": "tok1", "side": "SELL", "size": "10",
             "token_id": "tok1", "timestamp": str(int(time.time()))},
        ]
        reason = _check_exit_reason(client, pos)
        assert reason is None

    def test_profit_target_takes_priority_over_closing(self):
        # Both profit target AND market closing soon — profit_target checked first
        pos = _make_position(entry_price=0.5, profit_target_price=0.60, hours_until_end=5)
        client = _make_client(current_price=0.65)
        reason = _check_exit_reason(client, pos)
        assert reason == "profit_target"

    def test_no_exit_condition_returns_none(self):
        pos = _make_position(entry_price=0.5, hours_until_end=500)
        client = _make_client(current_price=0.52)  # below profit target
        client.get_trades.return_value = []
        reason = _check_exit_reason(client, pos)
        assert reason is None

    def test_price_api_failure_continues(self):
        pos = _make_position(entry_price=0.5, hours_until_end=500)
        client = _make_client()
        client.get_last_trade_price.side_effect = RuntimeError("API down")
        client.get_trades.return_value = []
        # Should not crash — just skip profit target check
        reason = _check_exit_reason(client, pos)
        assert reason is None
