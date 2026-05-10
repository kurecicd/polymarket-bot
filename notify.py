#!/usr/bin/env python3
"""
Telegram notifications. Sends alerts when trades are opened/closed
and a daily P&L summary.

Usage:
    from notify import send_trade_opened, send_trade_closed, send_daily_summary

Setup:
    1. Create a bot via @BotFather on Telegram → get TELEGRAM_BOT_TOKEN
    2. Start a chat with your bot, then get your chat ID:
       curl https://api.telegram.org/bot<TOKEN>/getUpdates
    3. Add both to .env
"""
import os
import logging
from datetime import datetime, timezone
from typing import Any

import requests

import common

log = logging.getLogger("notify")

TELEGRAM_BASE = "https://api.telegram.org"


def _send(message: str) -> bool:
    """Send a message to Telegram. Returns True on success."""
    common.load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not common.has_real_value(token) or not common.has_real_value(chat_id):
        log.debug("Telegram not configured — skipping notification")
        return False

    try:
        resp = requests.post(
            f"{TELEGRAM_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.warning(f"Telegram send failed: {exc}")
        return False


def send_trade_opened(position: dict, strategy: str = "whale") -> None:
    market = (position.get("market_question") or "?")[:60]
    entry = float(position.get("entry_price", 0))
    size = float(position.get("size_usdc", 0))
    target = float(position.get("profit_target_price", 0))
    whale = (position.get("whale_address") or "")[:12]
    tag = "QUICK BET" if strategy == "quick_bet" else f"WHALE {whale}..."

    msg = (
        f"<b>NEW TRADE [{tag}]</b>\n"
        f"Market: {market}\n"
        f"Entry: <code>{entry:.3f}</code>  Size: <code>${size:.2f}</code>\n"
        f"Target: <code>{target:.3f}</code> (+{((target/entry)-1)*100:.0f}%)"
    )
    _send(msg)


def send_trade_closed(position: dict, reason: str) -> None:
    market = (position.get("market_question") or "?")[:60]
    entry = float(position.get("entry_price", 0))
    exit_price = float(position.get("exit_price") or 0)
    pnl = float(position.get("realized_pnl") or 0)
    emoji = "GREEN" if pnl >= 0 else "RED"
    reason_map = {
        "profit_target": "Profit target hit",
        "whale_exiting": "Whale exiting",
        "market_closing_soon": "Market closing soon",
    }

    msg = (
        f"<b>TRADE CLOSED [{emoji}]</b>\n"
        f"Market: {market}\n"
        f"Entry: <code>{entry:.3f}</code>  Exit: <code>{exit_price:.3f}</code>\n"
        f"P&L: <b>${pnl:+.2f}</b>  |  {reason_map.get(reason, reason)}"
    )
    _send(msg)


def send_consensus_result(market: str, approved: bool, summary: str) -> None:
    status = "APPROVED" if approved else "REJECTED"
    msg = (
        f"<b>CONSENSUS {status}</b>\n"
        f"Market: {market[:60]}\n"
        f"<code>{summary}</code>"
    )
    _send(msg)


def send_daily_summary(execution_state: dict) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    log_entries = []
    if common.EXECUTION_LOG_PATH.exists():
        import json
        with common.EXECUTION_LOG_PATH.open() as fh:
            for line in fh:
                try:
                    log_entries.append(json.loads(line.strip()))
                except Exception:
                    pass

    today_closed = [
        e for e in log_entries
        if e.get("event") == "position_closed"
        and e.get("time", "").startswith(today)
    ]
    today_opened = [
        e for e in log_entries
        if e.get("event") == "copy_trade_opened"
        and e.get("time", "").startswith(today)
    ]

    total_pnl = sum(
        float((e.get("position") or {}).get("realized_pnl") or 0)
        for e in today_closed
    )
    wins = sum(
        1 for e in today_closed
        if float((e.get("position") or {}).get("realized_pnl") or 0) > 0
    )
    losses = len(today_closed) - wins
    open_count = sum(
        1 for p in execution_state.get("active_positions", {}).values()
        if p.get("status") == "open"
    )

    msg = (
        f"<b>DAILY SUMMARY — {today}</b>\n"
        f"Trades opened: {len(today_opened)}  |  Closed: {len(today_closed)}\n"
        f"Wins: {wins}  Losses: {losses}\n"
        f"Day P&L: <b>${total_pnl:+.2f}</b>\n"
        f"Still open: {open_count} positions"
    )
    _send(msg)


if __name__ == "__main__":
    # Test: sends a test message to verify config
    ok = _send("<b>Polymarket Bot</b> — Telegram notifications active!")
    print("Sent!" if ok else "Failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
