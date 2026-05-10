# Polymarket Whale Bot

## How We Make Money

Polymarket is a prediction market — people bet real money on real events ("Will Bitcoin hit $100k?", "Who wins the election?"). Some wallets are consistently right and make millions. We don't predict anything. We just **copy them**.

The strategy in plain English:
1. Find the 20 most profitable wallets on Polymarket (ranked by all-time P&L from the blockchain)
2. Watch them 24/7
3. When one of them places a new bet, we copy it immediately with a small portion of our balance
4. Before they exit, we exit — locking in profit without waiting for the market to resolve

Three conditions trigger an early exit:
- We're up **25%** on the position
- The whale starts **selling their position** (we get out before them)
- The market **closes in less than 72 hours**

An AI panel of 3 Claude agents reviews every signal before a trade is placed — one checks if the market odds make sense, one checks the whale's track record, one checks risk. At least 2 of 3 must approve.

Max **10 trades per day**, **2% of balance per trade**.

---

## How It Works Technically

```
DATA PIPELINE (runs once, refreshed weekly)
  Dune Analytics → 14,000 wallets ranked by all-time P&L
  (Polygon blockchain, CTF Exchange OrderFilled events)
  Top 20 profitable wallets → whale_list.json

MONITORING LOOP (every 60 seconds)
  poll data-api.polymarket.com/trades?user={whale}
  New BUY trade detected?
    → liquidity >= $10k?
    → market closes in > 72h?
    → daily limit < 10 trades?
    → 3-agent AI consensus passes?
    → place order via Polymarket CLOB API

POSITION MANAGER (every 5 minutes)
  For each open position:
    A. price >= entry x 1.25      → exit (profit target)
    B. whale sold >30% of entry   → exit (follow them out)
    C. market closes in < 72h     → exit (safety)
```

### Stack

| Layer | Tech |
|---|---|
| Data source | Dune Analytics (Polygon blockchain) + Polymarket public API |
| AI consensus | Claude Sonnet via Anthropic API |
| Backend API | FastAPI + Python on Railway |
| Frontend | Next.js 14 + Tailwind on Vercel |
| Storage | Railway persistent volume at /data |

### Key Files

| File | What it does |
|---|---|
| `dune_fetch.py` | Queries blockchain for all-time wallet P&L via Dune |
| `fetch_historical.py` | Fallback: collects wallets from public Polymarket API |
| `rank_wallets.py` | Computes win rates from trade data |
| `select_whales.py` | Picks top 20 wallets to monitor |
| `monitor.py` | Main loop — polls whales every 60s, copies trades |
| `position_manager.py` | Checks 3 exit conditions every 5 min |
| `consensus.py` | 3-agent Claude AI vote before every trade |
| `quick_bets.py` | Secondary strategy: finds mispriced markets |
| `notify.py` | Telegram alerts on trade open/close |
| `backtest.py` | Historical simulation to validate strategy |
| `api/` | FastAPI backend serving the web dashboard |
| `web/` | Next.js dashboard — live P&L, whale tracker, consensus log |

### Setup

```bash
git clone https://github.com/kurecicd/polymarket-bot
cd polymarket-bot && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in: POLYMARKET_PRIVATE_KEY, DUNE_API_KEY, ANTHROPIC_API_KEY

python dune_fetch.py && python rank_wallets.py && python select_whales.py
python monitor.py            # dry-run
python monitor.py --execute  # live
```

### Live Dashboard

https://polymarket-bot-damir.vercel.app

---

## Risk Warning

Copy-trading is not guaranteed profit. Whales can be wrong. Only trade with money you can afford to lose. Always observe in dry-run mode before going live.
