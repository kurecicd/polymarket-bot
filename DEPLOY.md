# Deployment Guide

## How it works

Every `git push` to `main` auto-deploys both services. No manual steps needed.

| Service | Platform | Auto-deploy | URL |
|---|---|---|---|
| Backend (FastAPI) | Railway | Yes — connected to GitHub | https://polymarket-bot-production-ae2d.up.railway.app |
| Frontend (Next.js) | Vercel | Yes — connected to GitHub | https://polymarket-bot-kurecicds-projects.vercel.app |

**Always use `https://polymarket-bot-kurecicds-projects.vercel.app` as the frontend URL** — it auto-updates on every deploy. The `polymarket-bot-damir.vercel.app` alias requires manual update each time and should be ignored.

---

## After every git push

```bash
git push
# Railway deploys automatically (~2 min)
# Vercel deploys automatically (~1 min)
# Done. No manual steps.
```

To verify both deployed:
```bash
# Railway - check health
curl https://polymarket-bot-production-ae2d.up.railway.app/health

# Vercel - check it loads
curl -s https://polymarket-bot-kurecicds-projects.vercel.app | head -5
```

---

## If Vercel auto-deploy fails

Check build logs:
```bash
cd web
npx vercel ls          # see recent deployments and status
npx vercel inspect <deployment-url> --logs  # get error details
```

Deploy manually if needed:
```bash
npx vercel --prod --yes   # run from repo root (NOT from web/)
```

---

## If Railway auto-deploy fails

```bash
railway link --project 388bd0ad-ad5f-429d-989f-7d3af599bc42
railway service polymarket-bot
railway up --detach --service polymarket-bot
```

---

## Key settings (never change these)

**Vercel dashboard** (vercel.com/kurecicds-projects/polymarket-bot/settings):
- Root Directory: `web`
- Deployment Protection: OFF
- Framework: Next.js

**Railway dashboard** (railway.com/project/388bd0ad-ad5f-429d-989f-7d3af599bc42):
- Volume mounted at `/data` (persistent storage)
- GitHub connected to `kurecicd/polymarket-bot` → auto-deploy on push
- DUNE_API_KEY, ANTHROPIC_API_KEY, POLYMARKET_PRIVATE_KEY set in Variables

---

## Switching bot to LIVE mode

Open https://polymarket-bot-kurecicds-projects.vercel.app → click **○ DRY-RUN** → confirm → **● LIVE**

The bot then runs automatically every 60 seconds. Mode persists across page refreshes and Railway restarts.

---

## First-time setup on a new Railway instance

1. Deploy the code (Railway auto-deploys from GitHub)
2. Add a Volume in Railway dashboard → mount at `/data`
3. Add env vars in Railway: `POLYMARKET_PRIVATE_KEY`, `DUNE_API_KEY`, `ANTHROPIC_API_KEY`
4. Open dashboard → click **RUN SETUP** — fetches 14k wallets, takes ~5 min
5. Done
