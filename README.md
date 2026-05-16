# Polymarket Whale Bot

An automated trading bot for [Polymarket](https://polymarket.com) that monitors top-performing wallets and exploits order book mispricings. Trades are placed via the Polymarket CLOB v2 API with 0% fees through a Builder profile.

---

## What It Does

### 1. Whale Copy Trading
Monitors 40 high-ROI wallets on Polymarket every 60 seconds. When a whale makes a new BUY trade on a liquid market (≥$10k liquidity, resolving within 45 days), the bot copies it proportionally using 2% of the available trading balance. Before copying, three Claude AI agents (Market Analyst, Whale Analyst, Risk Analyst) must all approve the trade.

### 2. Quick Bets (Mispricing Scanner)
Scans 200+ active markets and compares the listed price against a fair value derived from order book imbalance. When the gap (edge) exceeds 3%, the bot bets on the underpriced side. Filters: YES price between 10–90% (no near-certain outcomes), resolves within 45 days, ≥$10k liquidity.

### 3. Automatic Exit Management
Runs every 5 minutes and closes positions when:
- Price hits +20% profit target
- The copied whale sells >30% of their entry position
- Market resolves within 72 hours

---

## Architecture

```
polymarket-bot/
├── monitor.py              # Whale polling daemon (every 60s via APScheduler)
├── quick_bets.py           # Mispricing scanner
├── position_manager.py     # Exit condition checker (every 5min)
├── dune_fetch.py           # Wallet rankings from Dune Analytics (real ROI)
├── select_whales.py        # Picks top 40 wallets, fetches on-chain pUSD balances
├── polymarket_client.py    # Polymarket CLOB v2 API wrapper (py-clob-client-v2)
├── consensus.py            # 3-agent Claude AI trade approval
├── common.py               # Shared state, logging, blockchain balance queries
├── api/                    # FastAPI backend
│   ├── main.py             # APScheduler, debug endpoints, mode switching
│   └── routers/            # stats, positions, whales, activity, actions
├── web/                    # Next.js 14 dashboard (Vercel)
│   ├── app/
│   │   ├── page.tsx        # Server-rendered dashboard
│   │   ├── middleware.ts   # Password auth (HMAC cookie, Edge Runtime)
│   │   └── components/
│   │       ├── StatsBar        # Live balance, P&L, win rate
│   │       ├── HeatMap         # Category volume + open positions per sector
│   │       ├── WhaleTable      # 40 whales with ROI, balance, category breakdown
│   │       ├── PositionsTable  # Open/closed with CLOSE button, whale links
│   │       ├── ActivityFeed    # All events, button presses, CET/CEST times
│   │       ├── ConsensusLog    # AI agent vote results
│   │       ├── BotControls     # POLL / QUICK BET / CHECK EXITS / REFRESH WHALES
│   │       └── LiveStatus      # Real-time polling status
└── runtime/                # Persistent state (Railway volume /data)
    ├── execution_state.json    # Active positions, daily trade log
    ├── monitor_state.json      # Last-seen trade IDs per whale
    ├── whale_list.json         # Selected whales with ROI + balances
    ├── event_log.jsonl         # All bot events
    └── execution_log.jsonl     # All trades opened/closed
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Trading API | Polymarket CLOB v2 (`py-clob-client-v2`) |
| Order signing | EIP-1271 (POLY_1271) via deposit wallet proxy |
| Blockchain reads | Polygon JSON-RPC (pUSD balance, USDC allowance) |
| Wallet ranking | Dune Analytics SQL (realized P&L from CTF exchange events) |
| Whale monitoring | Polymarket data-api.polymarket.com (public, no auth) |
| AI consensus | Anthropic Claude (3 parallel agents via `anthropic` SDK) |
| Scheduler | APScheduler BackgroundScheduler in FastAPI |
| Backend | FastAPI + Uvicorn on Railway (EU West, persistent volume) |
| Frontend | Next.js 14 (App Router, server components) on Vercel |
| Frontend auth | HMAC-signed cookie, Web Crypto API, Edge Runtime |
| State storage | JSON/JSONL files on Railway persistent volume (`/data`) |
| Notifications | Telegram Bot API |

---

## Wallet Registration (CLOB v2)

Polymarket's CLOB v2 requires a **deposit wallet** (EIP-1271 smart contract wallet) deployed via their relayer:

```
POST https://relayer-v2.polymarket.com/submit
Headers: RELAYER_API_KEY, RELAYER_API_KEY_ADDRESS
Body: { "type": "WALLET-CREATE", "from": ownerAddress, "to": factoryAddress }
```

Orders are signed using `signatureType=3` (POLY_1271) with both maker and signer set to the deposit wallet address. The owner EOA signs on behalf of the smart contract wallet.

---

## Key Environment Variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `POLYMARKET_PRIVATE_KEY_RABBY` | Railway | Owner EOA private key |
| `POLYMARKET_FUNDER_ADDRESS` | Railway | Deposit wallet address |
| `POLYMARKET_BUILDER_CODE` | Railway | Builder code (0% fees) |
| `POLYMARKET_RELAYER_API_KEY` | Railway | Relayer API key for wallet ops |
| `DUNE_API_KEY` | Railway | Wallet ROI rankings |
| `ANTHROPIC_API_KEY` | Railway | Claude AI consensus |
| `TELEGRAM_BOT_TOKEN` | Railway | Trade notifications |
| `DASHBOARD_USERNAME` | Vercel | Dashboard login |
| `DASHBOARD_PASSWORD` | Vercel | Dashboard login |
| `DASHBOARD_SECRET` | Vercel | Cookie signing secret |

---

## Deployment

**Backend (Railway):** Auto-deploys on GitHub push. EU West region to avoid Polymarket geoblock. Persistent volume at `/data` survives redeploys.

**Frontend (Vercel):** Auto-deploys on GitHub push. Proxies all API calls to Railway to avoid CORS (`/api/proxy/*`).
