"use client";

import { useState, useEffect, useCallback } from "react";

interface Props {
  alreadyRunning?: boolean;
  stage?: string;
  rowsDownloaded?: number;
  walletsScanned?: number;
}

const STAGE_LABELS: Record<string, string> = {
  fetching:       "Fetching wallet rankings from Dune blockchain data…",
  ranking:        "Ranking wallets by win rate and profit…",
  selecting:      "Selecting top whale wallets…",
  done:           "✓ Done! Page will refresh automatically.",
  failed_no_trades: "⚠ Failed — no trade data fetched. Check Railway logs.",
  failed_ranking: "⚠ Failed at ranking step. Check Railway logs.",
  not_started:    "Not started yet.",
};

interface LiveStatus {
  setup_running: boolean;
  stage: string;
  data_ready: boolean;
  rows_downloaded: number;
  wallets_scanned: number;
  whale_count: number;
  trades_fetched: boolean;
  whales_selected: boolean;
}

export default function SetupBanner({ alreadyRunning = false, stage: initialStage = "", rowsDownloaded: initRows = 0, walletsScanned: initWallets = 0 }: Props) {
  const [running, setRunning] = useState(alreadyRunning);
  const [status, setStatus] = useState<LiveStatus>({
    setup_running: alreadyRunning,
    stage: initialStage,
    data_ready: false,
    rows_downloaded: initRows,
    wallets_scanned: initWallets,
    whale_count: 0,
    trades_fetched: false,
    whales_selected: false,
  });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);

  const RAILWAY_URL = "https://polymarket-bot-production-ae2d.up.railway.app";

  const pollStatus = useCallback(async () => {
    try {
      const res = await fetch(`${RAILWAY_URL}/api/actions/setup-status`);
      const data: LiveStatus = await res.json();
      setStatus(data);
      if (data.data_ready) {
        // Auto-reload the page when done
        setTimeout(() => window.location.reload(), 1500);
      }
      setRunning(data.setup_running);
    } catch {
      // silently ignore poll errors
    }
  }, []);

  // Poll every 8 seconds while running
  useEffect(() => {
    if (!running && !alreadyRunning) return;
    pollStatus();
    const interval = setInterval(pollStatus, 8000);
    return () => clearInterval(interval);
  }, [running, alreadyRunning, pollStatus]);

  // Elapsed time counter
  useEffect(() => {
    if (!running && !alreadyRunning) return;
    const interval = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(interval);
  }, [running, alreadyRunning]);

  async function startSetup() {
    setStarting(true);
    setError("");
    try {
      const res = await fetch(`${RAILWAY_URL}/api/actions/setup`, { method: "POST" }).then(r => r.json());
      if (res.status === "triggered" || res.status === "already_running") {
        setRunning(true);
        setElapsed(0);
        pollStatus();
      } else {
        setError("Unexpected response — try again");
      }
    } catch {
      setError("Failed to reach Railway backend");
    } finally {
      setStarting(false);
    }
  }

  const stage = status.stage || initialStage;
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  const elapsedStr = elapsed > 0 ? `${mins}m ${secs}s` : "";

  if (status.data_ready) {
    return (
      <div className="border border-green-700 bg-green-950/30 rounded p-3 mb-4 text-center text-green-400 text-sm font-bold">
        ✓ Setup complete — loading dashboard…
      </div>
    );
  }

  if (running || alreadyRunning) {
    return (
      <div className="border border-green-800 bg-green-950/20 rounded p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-green-400 font-bold text-sm">⚙ SETUP RUNNING ON RAILWAY</p>
          {elapsedStr && <p className="text-green-800 text-xs">{elapsedStr} elapsed</p>}
        </div>

        {/* Stage */}
        <p className="text-green-500 text-xs mb-3">
          {STAGE_LABELS[stage] ?? stage ?? "Initializing…"}
        </p>

        {/* Progress bars */}
        <div className="space-y-2 text-xs">
          <ProgressRow label="Fetch wallets from Dune" done={status.trades_fetched} active={stage === "fetching"} />
          <ProgressRow label="Rank by P&L"             done={!!(status.trades_fetched && stage !== "fetching")} active={stage === "ranking"} />
          <ProgressRow label="Select top whales"       done={status.whales_selected} active={stage === "selecting"} />
        </div>

        {/* Stats */}
        {(status.rows_downloaded > 0 || status.wallets_scanned > 0 || status.whale_count > 0) && (
          <div className="mt-3 flex gap-4 text-xs text-green-700">
            {status.rows_downloaded > 0 && <span>{status.rows_downloaded.toLocaleString()} rows</span>}
            {status.wallets_scanned > 0  && <span>{status.wallets_scanned.toLocaleString()} wallets</span>}
            {status.whale_count > 0      && <span>{status.whale_count} whales selected</span>}
          </div>
        )}

        <p className="text-green-900 text-xs mt-3">Auto-refreshes every 8 seconds · page reloads when done</p>
      </div>
    );
  }

  return (
    <div className="border border-yellow-700 bg-yellow-950/30 rounded p-4 mb-4 text-center">
      <p className="text-yellow-400 font-bold text-sm mb-1">⚠ NO DATA YET — BOT NOT READY</p>
      <p className="text-yellow-700 text-xs mb-3">
        Fetches 14,000+ wallet rankings from the Polygon blockchain via Dune Analytics,
        then selects the top 20 most profitable whales to monitor.
        Takes ~5 minutes.
      </p>
      {error && <p className="text-red-400 text-xs mb-2">{error}</p>}
      <button
        onClick={startSetup}
        disabled={starting}
        className="bg-yellow-600 hover:bg-yellow-500 disabled:opacity-40 text-black font-bold px-6 py-2 rounded text-sm"
      >
        {starting ? "Starting…" : "RUN SETUP ON RAILWAY"}
      </button>
    </div>
  );
}

function ProgressRow({ label, done, active }: { label: string; done: boolean; active: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={done ? "text-green-400" : active ? "text-yellow-400 animate-pulse" : "text-green-900"}>
        {done ? "✓" : active ? "▶" : "○"}
      </span>
      <span className={done ? "text-green-600" : active ? "text-yellow-400" : "text-green-900"}>
        {label}
      </span>
      {active && <span className="text-green-800 text-xs">running…</span>}
    </div>
  );
}
