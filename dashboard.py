#!/usr/bin/env python3
"""
Live terminal dashboard — refreshes every 5 seconds.
Matches the style from the screenshot: stats bar, whale tracker,
consensus activity log, and latest positions with P&L.

Run:
    python dashboard.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import common
from polymarket_client import PolymarketClient

REFRESH_SECONDS = 5
console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_env_client() -> PolymarketClient | None:
    common.load_env()
    key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    if not common.has_real_value(key):
        return None
    try:
        return PolymarketClient(private_key=key, chain_id=chain_id)
    except Exception:
        return None


def _read_jsonl_tail(path: Path, n: int = 30) -> list[dict]:
    if not path.exists():
        return []
    lines = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return lines[-n:]


def _pct_color(pct: float) -> str:
    if pct >= 0.6:
        return "bright_green"
    if pct >= 0.5:
        return "green"
    if pct >= 0.4:
        return "yellow"
    return "red"


def _pnl_color(val: float) -> str:
    return "bright_green" if val >= 0 else "red"


# ── Stats bar ─────────────────────────────────────────────────────────────────

def _build_stats_bar(execution_state: dict, client: PolymarketClient | None) -> Panel:
    balance = 0.0
    if client:
        try:
            balance = client.get_usdc_balance()
        except Exception:
            pass

    active = execution_state.get("active_positions", {})
    log_entries = _read_jsonl_tail(common.EXECUTION_LOG_PATH, 200)
    trade_events = [e for e in log_entries if e.get("event") == "copy_trade_opened"]
    close_events = [e for e in log_entries if e.get("event") == "position_closed"]

    total_trades = len(trade_events)
    wins = sum(1 for e in close_events if float((e.get("position") or {}).get("realized_pnl") or 0) > 0)
    win_rate = wins / len(close_events) if close_events else 0.0

    daily_count = common.count_todays_trades(execution_state)
    open_count = sum(1 for p in active.values() if p.get("status") == "open")

    # Avg hold hours
    hold_hours: list[float] = []
    for e in close_events:
        pos = e.get("position") or {}
        opened = pos.get("opened_at_ts")
        closed = pos.get("closed_at")
        if opened and closed:
            try:
                closed_ts = datetime.fromisoformat(closed.replace("Z", "+00:00")).timestamp()
                hold_hours.append((closed_ts - float(opened)) / 3600)
            except Exception:
                pass
    avg_hold = sum(hold_hours) / len(hold_hours) if hold_hours else 0.0

    stats = Text()
    stats.append(f"  ${balance:,.0f}  ", style="bold bright_green")
    stats.append("USDC  |  ", style="dim")
    stats.append(f"{total_trades}", style="bold white")
    stats.append(" trades  |  ", style="dim")
    stats.append(f"{win_rate:.1%}", style=f"bold {_pct_color(win_rate)}")
    stats.append(" win rate  |  ", style="dim")
    stats.append(f"{open_count}", style="bold cyan")
    stats.append(" open  |  ", style="dim")
    stats.append(f"{avg_hold:.1f}h", style="bold white")
    stats.append(" avg hold  |  ", style="dim")
    stats.append(f"{daily_count}/10", style="bold yellow")
    stats.append(" today  |  ", style="dim")
    stats.append(f"{len(active)}", style="bold white")
    stats.append(" tracked whales", style="dim")

    return Panel(stats, style="on black", box=box.HORIZONTALS)


# ── Whale tracker ─────────────────────────────────────────────────────────────

def _build_whale_table(whale_list: dict) -> Panel:
    whales = whale_list.get("whales", [])
    table = Table(
        show_header=True,
        header_style="bold green",
        box=box.SIMPLE,
        expand=True,
        style="green",
    )
    table.add_column("WALLET", style="dim", width=12)
    table.add_column("WIN%", justify="right", width=6)
    table.add_column("PROFIT", justify="right", width=10)
    table.add_column("TRADES", justify="right", width=7)

    for w in whales[:20]:
        addr = w["address"]
        short = f"{addr[:6]}...{addr[-4:]}"
        win_rate = float(w.get("win_rate", 0))
        profit = float(w.get("total_profit_usdc", 0))
        trades = int(w.get("total_trades", 0))
        table.add_row(
            short,
            Text(f"{win_rate:.0%}", style=_pct_color(win_rate)),
            Text(f"${profit:,.0f}", style="bright_green" if profit > 0 else "red"),
            str(trades),
        )

    count = len(whales)
    return Panel(
        table,
        title=f"[bold green]WHALE TRACKER // {count} WALLETS[/]",
        border_style="green",
        box=box.ROUNDED,
    )


# ── Consensus activity ────────────────────────────────────────────────────────

def _build_consensus_panel() -> Panel:
    events = _read_jsonl_tail(common.EVENT_LOG_PATH, 100)
    consensus_events = [e for e in events if e.get("event") == "vote_complete"][-12:]

    table = Table(show_header=False, box=box.SIMPLE, expand=True, style="green")
    table.add_column("TIME", width=6)
    table.add_column("RESULT", width=10)
    table.add_column("MARKET", no_wrap=False)

    for e in reversed(consensus_events):
        details = e.get("details", {})
        ts = e.get("time", "")
        time_str = ts[11:16] if len(ts) >= 16 else "?"
        approved = details.get("approved", False)
        buy_count = details.get("buy_count", 0)
        market = (details.get("market") or "?")[:45]
        result_text = Text(
            f"{'APPROVED' if approved else 'REJECTED'} {buy_count}/3",
            style="bright_green" if approved else "red",
        )
        table.add_row(time_str, result_text, market)

    if not consensus_events:
        table.add_row("--", Text("waiting...", style="dim"), "No consensus runs yet")

    return Panel(
        table,
        title="[bold green]3-AGENT CONSENSUS BOTS[/]",
        border_style="green",
        box=box.ROUNDED,
    )


# ── Latest positions ──────────────────────────────────────────────────────────

def _build_positions_panel(execution_state: dict, client: PolymarketClient | None) -> Panel:
    active = execution_state.get("active_positions", {})
    log_entries = _read_jsonl_tail(common.EXECUTION_LOG_PATH, 50)
    recent_closed = [
        e.get("position", {})
        for e in log_entries
        if e.get("event") == "position_closed"
    ][-5:]

    table = Table(show_header=True, header_style="bold green", box=box.SIMPLE, expand=True)
    table.add_column("MARKET", no_wrap=False)
    table.add_column("ENTRY", justify="right", width=7)
    table.add_column("NOW", justify="right", width=7)
    table.add_column("P&L", justify="right", width=9)
    table.add_column("STATUS", width=8)

    # Open positions first
    for pos in list(active.values())[:6]:
        if pos.get("status") != "open":
            continue
        market = (pos.get("market_question") or "?")[:40]
        entry = float(pos.get("entry_price", 0))
        current = 0.0
        if client:
            try:
                current = client.get_last_trade_price(pos["token_id"])
            except Exception:
                pass
        shares = float(pos.get("size_shares", 0))
        pnl = (current - entry) * shares if current > 0 else 0.0
        pnl_text = Text(f"${pnl:+.2f}", style=_pnl_color(pnl))
        now_text = Text(f"{current:.3f}" if current > 0 else "---", style="white")
        table.add_row(market, f"{entry:.3f}", now_text, pnl_text, Text("OPEN", style="cyan"))

    # Recent closed positions
    for pos in recent_closed:
        market = (pos.get("market_question") or "?")[:40]
        entry = float(pos.get("entry_price", 0))
        exit_price = float(pos.get("exit_price") or 0)
        pnl = float(pos.get("realized_pnl") or 0)
        reason = pos.get("close_reason", "closed")[:8]
        pnl_text = Text(f"${pnl:+.2f}", style=_pnl_color(pnl))
        table.add_row(
            market,
            f"{entry:.3f}",
            Text(f"{exit_price:.3f}" if exit_price else "---", style="dim"),
            pnl_text,
            Text(reason, style="dim"),
        )

    if not active and not recent_closed:
        table.add_row("No positions yet", "---", "---", "---", "---")

    return Panel(
        table,
        title="[bold green]LATEST POSITIONS[/]",
        border_style="green",
        box=box.ROUNDED,
    )


# ── Recent activity log ───────────────────────────────────────────────────────

def _build_activity_log() -> Panel:
    events = _read_jsonl_tail(common.EVENT_LOG_PATH, 200)
    interesting = [
        e for e in events
        if e.get("event") in {
            "copy_trade_opened", "position_closed", "vote_complete",
            "order_failed", "sell_order_failed", "daily_limit_reached",
        }
    ][-8:]

    lines = Text()
    for e in reversed(interesting):
        ts = e.get("time", "")
        time_str = ts[11:19] if len(ts) >= 19 else "?"
        event = e.get("event", "")
        details = e.get("details", {})

        if event == "copy_trade_opened":
            market = details.get("market", "?")[:45]
            color = "bright_green"
            msg = f"TRADE  {market}"
        elif event == "position_closed":
            reason = details.get("reason", "?")
            pnl = details.get("realized_pnl")
            pnl_str = f"  P&L: ${float(pnl):+.2f}" if pnl is not None else ""
            color = "bright_green" if (pnl and float(pnl) > 0) else "red"
            msg = f"CLOSE  {reason}{pnl_str}"
        elif event == "vote_complete":
            approved = details.get("approved", False)
            market = details.get("market", "?")[:35]
            color = "green" if approved else "dim"
            msg = f"VOTE   {'✓' if approved else '✗'} {market}"
        elif "failed" in event:
            color = "red"
            msg = f"ERROR  {event}"
        else:
            color = "dim"
            msg = f"{event}"

        lines.append(f"  {time_str}  ", style="dim")
        lines.append(f"{msg}\n", style=color)

    if not interesting:
        lines.append("  Waiting for activity...", style="dim")

    return Panel(lines, title="[bold green]ACTIVITY LOG[/]", border_style="green", box=box.ROUNDED)


# ── Main layout ───────────────────────────────────────────────────────────────

def _render(client: PolymarketClient | None) -> Layout:
    execution_state = common.load_execution_state()
    whale_list = common.read_json(common.WHALE_LIST_PATH) if common.WHALE_LIST_PATH.exists() else {"whales": []}

    layout = Layout()
    layout.split_column(
        Layout(name="stats", size=3),
        Layout(name="main"),
        Layout(name="log", size=12),
    )
    layout["main"].split_row(
        Layout(name="whales", ratio=1),
        Layout(name="consensus", ratio=1),
        Layout(name="positions", ratio=2),
    )

    layout["stats"].update(_build_stats_bar(execution_state, client))
    layout["whales"].update(_build_whale_table(whale_list))
    layout["consensus"].update(_build_consensus_panel())
    layout["positions"].update(_build_positions_panel(execution_state, client))
    layout["log"].update(_build_activity_log())

    return layout


def main() -> None:
    common.load_env()
    client = _load_env_client()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    console.print(f"\n[bold green]POLYMARKET WHALE BOT[/]  [dim]{now}[/]\n")

    if client is None:
        console.print("[yellow]Warning: POLYMARKET_PRIVATE_KEY not set — balance will show $0[/]\n")

    with Live(console=console, refresh_per_second=0.2, screen=True) as live:
        while True:
            try:
                live.update(_render(client))
            except Exception as exc:
                live.update(Panel(f"[red]Dashboard error: {exc}[/]"))
            time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped.[/]")
        sys.exit(0)
